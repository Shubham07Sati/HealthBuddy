import asyncio
import logging
from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded
from app.core.config import get_settings
from app.agents.orchestrator.pipeline import orchestrator
from app.schemas.agent_messages import DocumentEnvelope
import langchain
if not hasattr(langchain, "debug"):
    langchain.debug = False

settings = get_settings()
log = logging.getLogger(__name__)

celery_app = Celery(
    "lmis_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=4,

    # ROOT-CAUSE FIX: the celery_worker container (see docker-compose.yml)
    # is started with `-Q lmis_pipeline,lmis_ocr,lmis_ner,lmis_reasoning`
    # -- it never subscribes to Celery's default queue, "celery". Every
    # call site in this codebase publishes via `.delay(...)`, which without
    # an explicit route always lands on that default "celery" queue. The
    # result: tasks are accepted by Redis but no worker ever consumes them,
    # so `process_document_pipeline` (and any task) sits queued forever --
    # no exception, no timeout, no log line, just an upload that "hangs".
    #
    # task_routes pins this task onto a queue the worker actually reads
    # from. task_default_queue is also set so any *future* task added
    # without an explicit route fails the same way visibly (never
    # consumed, but at least consistent) rather than silently, and so a
    # bare `-Q` invocation without this task in task_routes still works.
    task_default_queue="lmis_pipeline",
    task_routes={
        "process_document_pipeline": {"queue": "lmis_pipeline"},
    },

    # Belt-and-suspenders: if a single document ever *does* wedge inside
    # an agent call (e.g. an LLM provider hangs with no timeout of its
    # own), this guarantees the worker kills the task instead of the
    # whole worker process going silently unresponsive. soft_time_limit
    # raises SoftTimeLimitExceeded first so the task can flag the
    # document as failed in the DB (see error_handler below); time_limit
    # is the hard kill a few seconds later if that doesn't work.
    task_soft_time_limit=600,
    task_time_limit=630,
)

def run_async(coro):
    """Helper to run async code inside Celery's sync worker context."""
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@celery_app.task(name="process_document_pipeline")
def process_document_pipeline(envelope_data: dict, patient_id: str):
    log.info(f"Starting pipeline for document {envelope_data.get('document_id')} (Patient: {patient_id})")
    
    # Initialize state
    initial_state = {
        "document_id": envelope_data.get('document_id'),
        "patient_id": patient_id,
        "document_envelope": envelope_data,
        "raw_extraction": None,
        "entity_set": None,
        "coded_entity_set": None,
        "trend_set": None,
        "retrieved_knowledge": None,
        "draft_insight_set": None,
        "verified_insight_set": None,
        "current_step": "Initializing",
        "error": None
    }
    
    # Execute LangGraph state machine
    try:
        final_state = run_async(orchestrator.run_pipeline(initial_state))
        log.info(f"Pipeline completed successfully for doc {envelope_data.get('document_id')}")
        return final_state
    except SoftTimeLimitExceeded:
        # task_soft_time_limit (see celery_app.conf above) tripped -- an
        # agent call hung well past any reasonable processing time (e.g.
        # an LLM provider with no client-side timeout of its own). Mark
        # the document failed so the frontend stops polling forever,
        # then re-raise so Celery still records the task itself as failed.
        log.error(f"Pipeline for doc {envelope_data.get('document_id')} exceeded "
                  f"soft time limit ({celery_app.conf.task_soft_time_limit}s) -- "
                  f"marking document as failed")
        run_async(_mark_document_failed(envelope_data.get("document_id"),
                                         "Processing exceeded time limit"))
        raise
    except Exception as e:
        log.error(f"Pipeline failed for doc {envelope_data.get('document_id')}: {e}",
                  exc_info=True)
        # Previously this just logged and re-raised with no DB write --
        # any exception raised BEFORE orchestrator.run_pipeline reaches
        # its own try/except per-node handling (e.g. run_pipeline itself
        # failing to start, a serialization error in initial_state, an
        # error thrown by the LangGraph checkpointer) left the Document
        # row stuck at its last status forever, since node_error_handler
        # inside the graph never got a chance to run. Persist failure
        # here too so this class of error is never silent.
        run_async(_mark_document_failed(envelope_data.get("document_id"), str(e)))
        raise


async def _mark_document_failed(document_id: str, reason: str) -> None:
    """Best-effort write of a terminal failed status, used only for
    failures that happen outside the LangGraph graph's own error
    handling (see node_error_handler in orchestrator/pipeline.py for
    the normal path)."""
    if not document_id:
        return
    try:
        from uuid import UUID
        from datetime import datetime, timezone
        from app.services.database import async_session_maker
        from app.models.document import Document, ProcessingStatus

        async with async_session_maker() as session:
            doc = await session.get(Document, UUID(document_id))
            if doc is None:
                log.warning(f"Document {document_id} not found while persisting "
                            f"failure status")
                return
            doc.processing_status = ProcessingStatus.failed
            doc.processed_at = datetime.now(timezone.utc)
            await session.commit()
    except Exception:
        log.exception(f"Failed to persist failure status for document "
                       f"{document_id} (reason was: {reason}) -- DB may be "
                       f"unreachable")

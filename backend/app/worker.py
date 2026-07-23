import asyncio
import logging
from celery import Celery
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
    worker_concurrency=4
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
    except Exception as e:
        log.error(f"Pipeline failed: {str(e)}")
        # In a real app, update Document status to failed in DB
        raise

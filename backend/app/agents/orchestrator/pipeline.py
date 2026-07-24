import logging
from datetime import datetime, timezone
from functools import wraps
from typing import TypedDict, Optional, Dict, Any
from uuid import UUID

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agents.ocr.agent import OCRAgent
from app.agents.phi_tokenization.agent import PHITokenizationAgent
from app.agents.ner.agent import NERAgent
from app.agents.normalization.agent import NormalizationAgent
from app.agents.trend.agent import TrendAgent
from app.agents.knowledge.agent import KnowledgeAgent
from app.agents.reasoning.agent import ReasoningAgent
from app.agents.verification.agent import VerificationAgent

from app.schemas.agent_messages import (
    DocumentEnvelope,
    RawExtraction,
    ClinicalEntitySet,
    CodedEntitySet,
    DraftInsightSet,
    TrendSet,
)
from app.models.document import Document, ProcessingStatus
from app.models.clinical_entity import ClinicalEntity
from app.models.insight import Insight
from app.services.database import async_session_maker

log = logging.getLogger(__name__)


class PipelineState(TypedDict):
    document_id: str
    patient_id: str
    document_envelope: Optional[dict]
    raw_extraction: Optional[dict]
    phi_tokenized_extraction: Optional[dict]
    entity_set: Optional[dict]
    coded_entity_set: Optional[dict]
    trend_set: Optional[dict]
    clinical_context: Optional[str]
    retrieved_knowledge: Optional[list]
    draft_insight_set: Optional[dict]
    verified_insight_set: Optional[dict]
    current_step: str
    error: Optional[Dict[str, Any]]


def guarded_node(step_name: str, status_enum: ProcessingStatus = None):
    """
    Wraps a node so one agent's failure doesn't crash the whole graph run.
    Also updates the DB processing_status so the frontend UI animation advances.
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, state: PipelineState) -> PipelineState:
            if state.get("error"):
                return state
            
            state["current_step"] = step_name
            
            if status_enum and state.get("document_id"):
                try:
                    from app.services.database import async_session_maker
                    from app.models.document import Document
                    from uuid import UUID
                    async with async_session_maker() as session:
                        doc = await session.get(Document, UUID(state["document_id"]))
                        if doc:
                            doc.processing_status = status_enum
                            await session.commit()
                except Exception as e:
                    log.warning(f"Failed to update document status to {status_enum}: {e}")

            try:
                return await fn(self, state)
            except Exception as exc:
                log.exception(
                    f"Pipeline failed at step '{step_name}' for doc {state.get('document_id')}"
                )
                state["error"] = {
                    "step": step_name,
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                return state
        return wrapper
    return decorator


def _route_on_error(state: PipelineState) -> str:
    return "error" if state.get("error") else "ok"


class Orchestrator:
    """
    Agent 9: Orchestrator
    Owns the LangGraph state machine that sequences the other agents,
    contains failures to the step that caused them, and persists final
    results to Postgres.

    Deliberately NOT a graph node here: ingestion/triage. That step runs
    synchronously in the upload API handler (see api/v1/documents.py)
    because it's cheap, non-LLM, and its output (the routing decision)
    determines whether a Celery job gets enqueued at all -- a document
    that fails quality checks should be rejected immediately with a fast
    response, not pushed through a queue only to be rejected later.
    """

    def __init__(self):
        self.ocr_agent = OCRAgent()
        self.phi_tokenization_agent = PHITokenizationAgent()
        self.ner_agent = NERAgent()
        self.normalization_agent = NormalizationAgent()
        self.trend_agent = TrendAgent()
        self.knowledge_agent = KnowledgeAgent()
        self.reasoning_agent = ReasoningAgent()
        self.verification_agent = VerificationAgent()

        # Dev/single-run tracing only -- does NOT survive across Celery
        # worker processes or restarts. Swap for AsyncPostgresSaver
        # (langgraph.checkpoint.postgres.aio) when you need real
        # crash-resume across retries; Postgres via node_persist below
        # is what's actually durable right now.
        self.checkpointer = MemorySaver()

        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(PipelineState)

        workflow.add_node("ocr", self.node_ocr)
        workflow.add_node("phi_tokenization", self.node_phi_tokenization)
        workflow.add_node("ner", self.node_ner)
        workflow.add_node("normalization", self.node_normalization)
        workflow.add_node("trend", self.node_trend)
        workflow.add_node("knowledge", self.node_knowledge)
        workflow.add_node("reasoning", self.node_reasoning)
        workflow.add_node("verification", self.node_verification)
        workflow.add_node("persist", self.node_persist)
        workflow.add_node("error_handler", self.node_error_handler)

        workflow.set_entry_point("ocr")

        # Every stage checks for an upstream failure before advancing,
        # rather than letting an exception propagate and kill the whole run.
        workflow.add_conditional_edges("ocr", _route_on_error, {"error": "error_handler", "ok": "phi_tokenization"})
        workflow.add_conditional_edges("phi_tokenization", _route_on_error, {"error": "error_handler", "ok": "ner"})
        workflow.add_conditional_edges("ner", _route_on_error, {"error": "error_handler", "ok": "normalization"})
        workflow.add_conditional_edges("normalization", _route_on_error, {"error": "error_handler", "ok": "trend"})
        workflow.add_conditional_edges("trend", _route_on_error, {"error": "error_handler", "ok": "knowledge"})
        workflow.add_conditional_edges("knowledge", _route_on_error, {"error": "error_handler", "ok": "reasoning"})
        workflow.add_conditional_edges("reasoning", _route_on_error, {"error": "error_handler", "ok": "verification"})
        workflow.add_conditional_edges("verification", _route_on_error, {"error": "error_handler", "ok": "persist"})

        workflow.add_edge("persist", END)
        workflow.add_edge("error_handler", END)

        return workflow.compile(checkpointer=self.checkpointer)

    # ------------------------------------------------------------------ #
    # Nodes                                                               #
    # ------------------------------------------------------------------ #
    @guarded_node("OCR & Layout Extraction", ProcessingStatus.ocr)
    async def node_ocr(self, state: PipelineState) -> PipelineState:
        envelope = DocumentEnvelope(**state["document_envelope"])
        result = await self.ocr_agent.extract(envelope)
        state["raw_extraction"] = result.model_dump(mode="json")
        return state

    @guarded_node("PHI Tokenization", ProcessingStatus.ocr)
    async def node_phi_tokenization(self, state: PipelineState) -> PipelineState:
        raw = RawExtraction(**state["raw_extraction"])
        result = await self.phi_tokenization_agent.tokenize(raw)
        state["phi_tokenized_extraction"] = result.model_dump(mode="json")
        return state

    @guarded_node("Medical NER", ProcessingStatus.ner)
    async def node_ner(self, state: PipelineState) -> PipelineState:
        # NER runs on the PHI-tokenized extraction (not the raw OCR
        # output) so patient identifiers never reach entity extraction
        # or any downstream agent/LLM call.
        raw = RawExtraction(**state["phi_tokenized_extraction"])
        result = await self.ner_agent.extract_entities(raw, state["patient_id"])
        state["entity_set"] = result.model_dump(mode="json")
        return state

    @guarded_node("Normalization & Coding", ProcessingStatus.normalizing)
    async def node_normalization(self, state: PipelineState) -> PipelineState:
        entity_set = ClinicalEntitySet(**state["entity_set"])
        result = await self.normalization_agent.normalize(entity_set)
        state["coded_entity_set"] = result.model_dump(mode="json")
        return state

    @guarded_node("Trend Analysis", ProcessingStatus.trend_analysis)
    async def node_trend(self, state: PipelineState) -> PipelineState:
        entity_set = ClinicalEntitySet(**state["entity_set"])
        coded_set = CodedEntitySet(**state["coded_entity_set"])
        result = await self.trend_agent.analyze_trends(entity_set, coded_set)
        state["trend_set"] = result.model_dump(mode="json")
        return state

    @guarded_node("Knowledge Retrieval", ProcessingStatus.reasoning)
    async def node_knowledge(self, state: PipelineState) -> PipelineState:
        entity_set = ClinicalEntitySet(**state["entity_set"]) if state.get("entity_set") else None
        coded_set = CodedEntitySet(**state["coded_entity_set"]) if state.get("coded_entity_set") else None
        trend_set = TrendSet(**state["trend_set"]) if state.get("trend_set") else None
        result = await self.knowledge_agent.retrieve_guidelines(
            entity_set=entity_set,
            coded_set=coded_set,
            trend_set=trend_set,
            clinical_context=state.get("clinical_context"),
            patient_id=UUID(state["patient_id"]),
        )
        state["retrieved_knowledge"] = result
        return state

    @guarded_node("Clinical Reasoning", ProcessingStatus.reasoning)
    async def node_reasoning(self, state: PipelineState) -> PipelineState:
        entity_set = ClinicalEntitySet(**state["entity_set"]) if state.get("entity_set") else None
        coded_set = CodedEntitySet(**state["coded_entity_set"]) if state.get("coded_entity_set") else None
        trend_set = TrendSet(**state["trend_set"]) if state.get("trend_set") else None
        result = await self.reasoning_agent.generate_insights(
            patient_id=UUID(state["patient_id"]),
            entity_set=entity_set,
            coded_set=coded_set,
            trend_set=trend_set,
            retrieved_guidelines=state.get("retrieved_knowledge") or [],
        )
        state["draft_insight_set"] = result.model_dump(mode="json")
        return state

    @guarded_node("Verification", ProcessingStatus.verifying)
    async def node_verification(self, state: PipelineState) -> PipelineState:
        draft_set = DraftInsightSet(**state["draft_insight_set"])
        result = await self.verification_agent.verify(draft_set)
        state["verified_insight_set"] = result.model_dump(mode="json")
        return state

    @guarded_node("Persisting results")
    async def node_persist(self, state: PipelineState) -> PipelineState:
        async with async_session_maker() as session:
            await self._persist_document_status(session, state, ProcessingStatus.complete)
            await self._persist_entities(session, state)
            await self._persist_trends(session, state)
            await self._persist_insights(session, state)
            await session.commit()
        state["current_step"] = "Complete"
        return state

    async def node_error_handler(self, state: PipelineState) -> PipelineState:
        log.error(f"Pipeline for doc {state.get('document_id')} ended in error: {state.get('error')}")
        try:
            async with async_session_maker() as session:
                await self._persist_document_status(session, state, ProcessingStatus.failed)
                await session.commit()
        except Exception:
            log.exception("Failed to persist failure status -- DB may be unreachable")
        return state

    # ------------------------------------------------------------------ #
    # Persistence helpers                                                 #
    # ------------------------------------------------------------------ #
    async def _persist_document_status(self, session, state: PipelineState, status: "ProcessingStatus"):
        doc_id = state.get("document_id")
        if not doc_id:
            return
        doc = await session.get(Document, UUID(doc_id))
        if doc is None:
            log.warning(f"Document {doc_id} not found in DB during persistence -- skipping status update")
            return
        doc.processing_status = status
        if status in (ProcessingStatus.complete, ProcessingStatus.failed):
            doc.processed_at = datetime.now(timezone.utc)

    async def _persist_entities(self, session, state: PipelineState):
        """
        Merge ExtractedEntity (from entity_set) with CodedEntity (from
        coded_entity_set) via temp_id, then write ClinicalEntity rows.
        Unmatched entities are persisted too (verification_status stays
        'unverified', no canonical_code) so nothing NER found silently
        disappears just because Normalization couldn't code it.
        """
        entity_set = state.get("entity_set")
        coded_set = state.get("coded_entity_set")
        if not entity_set:
            return

        # Fetch document for date fallback
        doc_id = state.get("document_id")
        doc = await session.get(Document, UUID(doc_id)) if doc_id else None
        doc_date = None
        if doc:
            doc_date = doc.document_date or doc.uploaded_at

        raw_by_temp_id = {e["temp_id"]: e for e in entity_set["entities"]}
        coded_by_temp_id = {c["temp_id"]: c for c in (coded_set or {}).get("coded_entities", [])}

        for temp_id, raw in raw_by_temp_id.items():
            coded = coded_by_temp_id.get(temp_id)
            session.add(ClinicalEntity(
                document_id=UUID(str(entity_set["document_id"])),
                patient_id=UUID(str(entity_set["patient_id"])),
                entity_type=raw["entity_type"],
                raw_value=raw["raw_value"],
                entity_label=raw.get("entity_label"),
                normalized_value=coded["normalized_value"] if coded else None,
                unit_raw=raw.get("unit_raw"),
                unit_canonical=coded.get("unit_canonical") if coded else None,
                canonical_code=coded.get("canonical_code") if coded else None,
                coding_system=coded.get("coding_system") if coded else None,
                confidence=coded["coding_confidence"] if coded else raw["combined_confidence"],
                ocr_confidence=raw["ocr_confidence"],
                ner_confidence=raw["ner_confidence"],
                source_span_start=raw["source_span_start"],
                source_span_end=raw["source_span_end"],
                source_bounding_box=raw.get("source_bounding_box"),
                entity_date=raw.get("entity_date") or doc_date,
                is_negated=raw["is_negated"],
                assertion_status=raw["assertion_status"],
                verification_status="unverified",
                reference_range_low=coded.get("reference_range_low") if coded else None,
                reference_range_high=coded.get("reference_range_high") if coded else None,
                reference_range_unit=coded.get("reference_range_unit") if coded else None,
            ))

    async def _persist_trends(self, session, state: PipelineState):
        trend_set = state.get("trend_set")
        if not trend_set:
            return
            
        from app.models.trend import Trend
        from datetime import datetime
        
        for t in trend_set.get("trends", []):
            start_date_str = t["data_points"][0]["timestamp"] if t["data_points"] else None
            end_date_str = t["data_points"][-1]["timestamp"] if t["data_points"] else None
            
            start_date = datetime.fromisoformat(start_date_str) if start_date_str else datetime.now(timezone.utc)
            end_date = datetime.fromisoformat(end_date_str) if end_date_str else datetime.now(timezone.utc)

            session.add(Trend(
                patient_id=UUID(str(trend_set["patient_id"])),
                metric_name=t["metric_name"],
                metric_canonical_code=t["metric_canonical_code"],
                direction=t["direction"],
                rate_of_change=t.get("rate_of_change"),
                trend_start_date=start_date,
                trend_end_date=end_date,
                data_point_count=len(t["data_points"]),
                statistical_confidence=t["statistical_confidence"],
                p_value=t.get("p_value"),
                change_point_date=t.get("change_point_date"),
                is_clinically_significant=t.get("is_clinically_significant", False),
                clinical_significance_reason=t.get("clinical_significance_reason"),
            ))

    async def _persist_insights(self, session, state: PipelineState):
        verified_set = state.get("verified_insight_set")
        if not verified_set:
            return

        for vi in verified_set["verified_insights"]:
            session.add(Insight(
                patient_id=UUID(str(verified_set["patient_id"])),
                draft_text=vi["final_text"],
                final_text=vi["final_text"],
                supporting_entity_ids=(
                    [str(x) for x in vi["supporting_entity_ids"]]
                    if vi.get("supporting_entity_ids") else None
                ),
                model_inference_flag=True,
                verification_status=self._map_verification_status(vi["verification_status"]),
                verification_confidence=vi["verification_confidence"],
                verification_rationale=vi["verification_rationale"],
                rejected_assertions=vi.get("rejected_assertions") or None,
                severity=vi["severity"],
                requires_clinician_review=vi["requires_clinician_review"],
                patient_facing_text=vi["patient_facing_text"],
                clinician_facing_text=vi["clinician_facing_text"],
            ))

    @staticmethod
    def _map_verification_status(agent_status: str) -> str:
        """
        SCHEMA MISMATCH, flagged for whoever owns agent_messages.py /
        insight.py: VerifiedInsight.verification_status uses
        VerificationStatus (clinical_entity.py): auto_verified /
        unverified / human_corrected / flagged. The Insight DB model uses
        a DIFFERENT enum, InsightVerificationStatus: pending / approved /
        rejected / modified / unverified_informational. They don't share
        values, so this mapping is a real editorial decision, not a type
        cast -- worth confirming this is the mapping you actually want:
        """
        mapping = {
            "auto_verified": "approved",
            "flagged": "pending",
            "unverified": "unverified_informational",
            "human_corrected": "modified",
        }
        return mapping.get(agent_status, "pending")

    # ------------------------------------------------------------------ #
    # Entry point                                                         #
    # ------------------------------------------------------------------ #
    async def run_pipeline(self, initial_state: PipelineState):
        config = {"configurable": {"thread_id": initial_state["document_id"]}}
        return await self.graph.ainvoke(initial_state, config=config)


orchestrator = Orchestrator()
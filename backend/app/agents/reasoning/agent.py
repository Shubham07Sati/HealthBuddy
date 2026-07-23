"""
Agent 6: Clinical Reasoning
============================
Consumes normalized/coded clinical entities (Agent 4), trend analysis
(Agent 5), and retrieved clinical knowledge (Agent 8), and drafts
evidence-grounded clinical insights for the Verification Agent (Agent 7)
to critique before anything reaches a clinician or patient.

Design contract this agent upholds:
  * Never invents patient data. The LLM is only ever shown a closed
    evidence pool built deterministically from upstream agent output
    (see evidence.py); every insight must cite evidence_ids drawn from
    that pool, and any candidate that cites an evidence_id outside the
    pool is dropped before it ever becomes a DraftInsight.
  * supporting_entity_ids on every DraftInsight is derived by this
    agent from the evidence the model cited -- never accepted verbatim
    from the model, since asking an LLM to emit UUIDs for data it
    didn't generate is an invitation to fabricate them.
  * Severity/confidence/insight_type are constrained to the same
    enums/literals used elsewhere in the pipeline (InsightSeverity,
    DraftInsight.insight_type), enforced structurally via `instructor`
    rather than by post-hoc string matching.
"""
import logging
import time
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.exceptions import ReasoningError
from app.models.insight import InsightSeverity
from app.schemas.agent_messages import (
    ClinicalEntitySet,
    CodedEntitySet,
    DraftInsight,
    DraftInsightSet,
    EvidenceItem,
    TrendSet,
)
from app.services.llm_provider import llm

from . import prompts
from .evidence import build_evidence_pool
from .models import EvidencePoolEntry, LLMInsightCandidate, LLMInsightResponse

log = logging.getLogger(__name__)
settings = get_settings()


class ReasoningAgent:
    """
    Agent 6: Clinical Reasoning (Generator)
    Generates potential clinical insights based on longitudinal data
    (trends, gaps, medications, lab values) and retrieved guidelines.
    """

    def __init__(self) -> None:
        self.model = settings.generator_model
        self.max_insights = settings.reasoning_max_insights
        self.min_confidence = settings.reasoning_min_confidence
        self.min_evidence_relevance = settings.reasoning_min_evidence_relevance

    async def generate_insights(
        self,
        patient_id: UUID,
        entity_set: Optional[ClinicalEntitySet],
        coded_set: Optional[CodedEntitySet],
        trend_set: Optional[TrendSet],
        retrieved_guidelines: List[dict],
    ) -> DraftInsightSet:
        """
        Build the evidence pool from upstream agent output, ask the LLM
        to draft insights strictly grounded in that pool, and translate
        its response into DraftInsight objects the Verification Agent
        can validate.

        Never raises for "no evidence" / "no insights" -- those are
        valid, common outcomes and return an empty DraftInsightSet.
        Raises ReasoningError for genuine failures (LLM unreachable,
        malformed structured output) so the orchestrator's guarded_node
        can route to error handling instead of silently losing data.
        """
        start_time = time.time()
        log.info(f"Generating clinical reasoning for patient {patient_id}")

        evidence_pool = build_evidence_pool(
            entity_set=entity_set,
            coded_set=coded_set,
            trend_set=trend_set,
            retrieved_guidelines=retrieved_guidelines,
            min_relevance=self.min_evidence_relevance,
        )

        if not evidence_pool:
            log.info(
                f"No evidence available for patient {patient_id} -- "
                "skipping LLM call, returning empty insight set"
            )
            return DraftInsightSet(
                patient_id=patient_id,
                insights=[],
                evidence_used=[],
                generator_model=self.model,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

        try:
            llm_response = await self._draft_candidates(evidence_pool)
        except Exception as exc:
            log.exception(f"Reasoning LLM call failed for patient {patient_id}")
            raise ReasoningError(
                message="Failed to generate clinical insights via LLM",
                detail=str(exc),
                patient_id=str(patient_id),
            ) from exc

        drafts, used_evidence_ids = self._to_draft_insights(llm_response, evidence_pool, patient_id)

        evidence_used = [
            EvidenceItem(
                evidence_id=e.evidence_id,
                source_type=e.source_type,
                source_ref=e.source_ref,
                text=e.text,
                relevance_score=e.relevance_score,
            )
            for eid, e in evidence_pool.items()
            if eid in used_evidence_ids
        ]

        log.info(
            f"Reasoning produced {len(drafts)} draft insight(s) for patient {patient_id} "
            f"from {len(evidence_pool)} evidence item(s)"
        )

        return DraftInsightSet(
            patient_id=patient_id,
            insights=drafts,
            evidence_used=evidence_used,
            generator_model=self.model,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )

    # ------------------------------------------------------------------ #
    # LLM interaction
    # ------------------------------------------------------------------ #
    async def _draft_candidates(self, evidence_pool: Dict[str, EvidencePoolEntry]) -> LLMInsightResponse:
        messages = prompts.build_messages(evidence_pool, self.max_insights)
        response = await llm.get_structured_completion(
            messages=messages,
            response_model=LLMInsightResponse,
            model=self.model,
        )
        if not isinstance(response, LLMInsightResponse):
            # Defensive: instructor should already guarantee this, but a
            # provider-specific code path (e.g. the Gemini fallback in
            # llm_provider.py) could in principle hand back something else.
            raise ReasoningError(message="LLM returned an unexpected response type")
        return response

    # ------------------------------------------------------------------ #
    # Candidate -> DraftInsight translation
    # ------------------------------------------------------------------ #
    def _to_draft_insights(
        self,
        llm_response: LLMInsightResponse,
        evidence_pool: Dict[str, EvidencePoolEntry],
        patient_id: UUID,
    ) -> "tuple[List[DraftInsight], set]":
        drafts: List[DraftInsight] = []
        used_evidence_ids: set = set()

        for candidate in llm_response.insights[: self.max_insights]:
            draft = self._validate_and_build(candidate, evidence_pool, patient_id)
            if draft is None:
                continue
            drafts.append(draft)
            used_evidence_ids.update(draft.supporting_evidence_ids)

        return drafts, used_evidence_ids

    def _validate_and_build(
        self,
        candidate: LLMInsightCandidate,
        evidence_pool: Dict[str, EvidencePoolEntry],
        patient_id: UUID,
    ) -> Optional[DraftInsight]:
        # Drop any evidence_id the model cited that isn't in the pool we
        # actually gave it -- this is the enforcement point for "never
        # invent patient data": a hallucinated evidence_id is dropped,
        # not trusted.
        valid_evidence_ids = [eid for eid in candidate.evidence_ids if eid in evidence_pool]
        dropped = set(candidate.evidence_ids) - set(valid_evidence_ids)
        if dropped:
            log.warning(
                f"Discarding unknown evidence_id(s) cited by LLM for patient {patient_id}: "
                f"{sorted(dropped)}"
            )

        if not valid_evidence_ids:
            log.warning(
                f"Discarding insight candidate for patient {patient_id} -- "
                "no valid evidence_ids after filtering (unsupported claim)"
            )
            return None

        if candidate.confidence < self.min_confidence:
            log.info(
                f"Discarding insight candidate for patient {patient_id} -- "
                f"confidence {candidate.confidence:.2f} below threshold {self.min_confidence:.2f}"
            )
            return None

        supporting_entity_ids: List[UUID] = []
        seen = set()
        for eid in valid_evidence_ids:
            for entity_id_str in evidence_pool[eid].entity_ids:
                if entity_id_str not in seen:
                    seen.add(entity_id_str)
                    try:
                        supporting_entity_ids.append(UUID(entity_id_str))
                    except ValueError:
                        log.warning(f"Skipping malformed entity_id on evidence {eid}: {entity_id_str}")

        try:
            severity = InsightSeverity(candidate.severity)
        except ValueError:
            log.warning(
                f"LLM returned unrecognized severity '{candidate.severity}' for patient {patient_id}; "
                "defaulting to 'informational'"
            )
            severity = InsightSeverity.informational

        clinician_text = candidate.clinician_facing_text.strip()
        patient_text = candidate.patient_facing_text.strip()
        if not clinician_text or not patient_text:
            log.warning(
                f"Discarding insight candidate for patient {patient_id} -- "
                "missing clinician- or patient-facing text"
            )
            return None

        return DraftInsight(
            draft_id=uuid4().hex,
            text=clinician_text,
            supporting_entity_ids=supporting_entity_ids,
            supporting_evidence_ids=valid_evidence_ids,
            model_inference_flag=True,
            severity=severity,
            confidence=round(float(candidate.confidence), 4),
            patient_facing_text=patient_text,
            clinician_facing_text=clinician_text,
            insight_type=candidate.insight_type,
        )
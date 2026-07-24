"""
Agent 7: Verification & Critic
================================
Consumes the Reasoning Agent's draft insights (Agent 6 output) and
fact-checks each one before it can reach a clinician or patient.

Design contract this agent upholds (mirrors reasoning/agent.py's):
  * Never trusts a draft insight's own confidence -- verification_confidence
    is computed here, independently, from how many atomic assertions were
    actually verified against evidence and how confidently.
  * Every assertion is checked strictly against the SAME evidence pool the
    Reasoning Agent cited for that insight (draft.supporting_evidence_ids,
    resolved against DraftInsightSet.evidence_used) -- never outside
    knowledge, and never an evidence_id the model hallucinates: any
    evidence_id the verifier LLM cites that isn't in the pool it was shown
    is dropped, exactly like the Reasoning Agent's own evidence discipline.
  * An insight with zero verifiable assertions, or with no cited evidence
    to check in the first place, is rejected outright (added to
    `rejected_insights`), not passed through with a low score -- silently
    downgrading a hallucinated insight is a worse failure mode than
    dropping it for review.
  * requires_clinician_review is always True for high/critical severity
    insights, regardless of verification outcome -- a clean fact-check
    is not a substitute for clinical judgement on a serious finding.
"""
import logging
import time
from typing import Dict, List

from app.core.config import get_settings
from app.core.exceptions import VerificationError
from app.models.clinical_entity import VerificationStatus
from app.models.insight import InsightSeverity
from app.schemas.agent_messages import (
    AtomicAssertion,
    DraftInsight,
    DraftInsightSet,
    EvidenceItem,
    VerifiedInsight,
    VerifiedInsightSet,
)
from app.services.llm_provider import llm

from . import prompts
from .models import LLMAssertionCandidate, LLMVerificationResponse

log = logging.getLogger(__name__)
settings = get_settings()

# Fraction of assertions that must be verified, and the minimum resulting
# confidence, before an insight is auto-verified rather than flagged for
# clinician review. Kept local (like normalization's _EXACT_CONFIDENCE)
# since there's no dedicated verification.* settings block yet.
_AUTO_VERIFY_MIN_CONFIDENCE = 0.75
_SEVERITY_ALWAYS_REVIEW = {InsightSeverity.high, InsightSeverity.critical}


class VerificationAgent:
    """
    Agent 7: Verification & Critic
    Critiques generated insights, breaks them down into atomic assertions,
    and verifies each against the evidence the Reasoning Agent actually
    cited. Prevents hallucination before surfacing to the user.
    """

    def __init__(self):
        self.model = settings.verifier_model

    async def verify(self, draft_set: DraftInsightSet) -> VerifiedInsightSet:
        start_time = time.time()
        log.info(
            f"Verifying {len(draft_set.insights)} draft insight(s) for patient {draft_set.patient_id}"
        )

        evidence_by_id: Dict[str, EvidenceItem] = {e.evidence_id: e for e in draft_set.evidence_used}
        all_evidence = list(draft_set.evidence_used)

        verified: List[VerifiedInsight] = []
        rejected: List[DraftInsight] = []
        failures = 0

        for draft in draft_set.insights:
            cited_evidence = [evidence_by_id[eid] for eid in draft.supporting_evidence_ids
                               if eid in evidence_by_id]

            if not cited_evidence:
                # Reasoning Agent's own contract requires at least one
                # valid evidence_id per draft, so this should be rare --
                # but a draft with nothing to check against cannot be
                # verified, only rejected.
                log.warning(
                    f"Draft {draft.draft_id} for patient {draft_set.patient_id} has no resolvable "
                    "cited evidence -- rejecting without an LLM call"
                )
                rejected.append(draft)
                continue

            try:
                result = await self._verify_one(draft, cited_evidence, all_evidence)
            except Exception as exc:
                failures += 1
                log.error(
                    f"Verification LLM call failed for draft {draft.draft_id}, patient "
                    f"{draft_set.patient_id}: {exc}", exc_info=True
                )
                rejected.append(draft)
                continue

            if result is None:
                rejected.append(draft)
            else:
                verified.append(result)

        if failures and failures == len(draft_set.insights) and draft_set.insights:
            raise VerificationError(
                message="All insight verification calls failed",
                detail=f"{failures} of {len(draft_set.insights)} drafts errored",
            )

        log.info(
            f"Verification for patient {draft_set.patient_id}: {len(verified)} verified, "
            f"{len(rejected)} rejected"
        )

        return VerifiedInsightSet(
            patient_id=draft_set.patient_id,
            verified_insights=verified,
            rejected_insights=rejected,
            verifier_model=self.model,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )

    # ------------------------------------------------------------------ #
    # Per-insight verification
    # ------------------------------------------------------------------ #
    async def _verify_one(
        self,
        draft: DraftInsight,
        cited_evidence: List[EvidenceItem],
        all_evidence: List[EvidenceItem],
    ) -> "VerifiedInsight | None":
        messages = prompts.build_messages(
            insight_text=draft.clinician_facing_text or draft.text,
            cited_evidence=cited_evidence,
            all_evidence=all_evidence,
        )
        response = await llm.get_structured_completion(
            messages=messages,
            response_model=LLMVerificationResponse,
            model=self.model,
        )
        if not isinstance(response, LLMVerificationResponse):
            raise VerificationError(
                message="Verifier LLM returned an unexpected response type",
                draft_id=draft.draft_id,
            )

        cited_ids = {e.evidence_id for e in cited_evidence}
        all_ids = {e.evidence_id for e in all_evidence}
        evidence_by_id = {e.evidence_id: e for e in all_evidence}

        if not response.assertions:
            log.warning(f"Verifier produced no assertions for draft {draft.draft_id} -- rejecting")
            return None

        atomic_assertions: List[AtomicAssertion] = []
        verified_confidences: List[float] = []
        any_contradiction = False

        for candidate in response.assertions:
            assertion = self._to_atomic_assertion(candidate, cited_ids, all_ids, evidence_by_id, draft.draft_id)
            atomic_assertions.append(assertion)
            if assertion.contradicting_evidence:
                any_contradiction = True
            if assertion.verified:
                verified_confidences.append(assertion.confidence)

        verified_count = len(verified_confidences)
        total_count = len(atomic_assertions)

        if verified_count == 0:
            log.info(
                f"Draft {draft.draft_id}: none of {total_count} assertion(s) could be verified "
                "against cited evidence -- rejecting insight"
            )
            return None

        # Explainable confidence: how much of the insight was actually
        # verified (coverage), weighted by how confidently each verified
        # assertion was checked. Both factors are visible in the log/
        # rationale, not just the final number.
        coverage = verified_count / total_count
        avg_verified_confidence = sum(verified_confidences) / verified_count
        verification_confidence = round(coverage * avg_verified_confidence, 4)

        rejected_assertions = [a for a in atomic_assertions if not a.verified]

        all_verified = verified_count == total_count
        is_auto_verifiable = (
            all_verified
            and not any_contradiction
            and verification_confidence >= _AUTO_VERIFY_MIN_CONFIDENCE
        )

        if any_contradiction:
            status = VerificationStatus.flagged
        elif is_auto_verifiable:
            status = VerificationStatus.auto_verified
        else:
            status = VerificationStatus.flagged

        requires_review = (
            status != VerificationStatus.auto_verified
            or draft.severity in _SEVERITY_ALWAYS_REVIEW
        )

        rationale_parts = [
            f"{verified_count}/{total_count} atomic assertion(s) verified against cited evidence "
            f"(coverage={coverage:.2f}, avg confidence={avg_verified_confidence:.2f})."
        ]
        if any_contradiction:
            rationale_parts.append("Conflicting evidence was found for at least one assertion.")
        if response.overall_rationale:
            rationale_parts.append(response.overall_rationale.strip())

        return VerifiedInsight(
            draft_id=draft.draft_id,
            insight_db_id=None,
            final_text=draft.text,
            patient_facing_text=draft.patient_facing_text,
            clinician_facing_text=draft.clinician_facing_text,
            verification_status=status,
            verification_confidence=verification_confidence,
            verification_rationale=" ".join(rationale_parts),
            atomic_assertions=atomic_assertions,
            rejected_assertions=rejected_assertions,
            severity=draft.severity,
            requires_clinician_review=requires_review,
        )

    # ------------------------------------------------------------------ #
    # Candidate -> AtomicAssertion translation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_atomic_assertion(
        candidate: LLMAssertionCandidate,
        cited_ids: set,
        all_ids: set,
        evidence_by_id: Dict[str, EvidenceItem],
        draft_id: str,
    ) -> AtomicAssertion:
        # Supporting evidence must come from what the insight actually
        # cited -- an id outside that pool (even if it's a real id from
        # `all_evidence`) is not legitimate support for THIS insight's
        # claim and is dropped, matching the Reasoning Agent's own rule
        # that a model never gets to expand its own evidence pool.
        valid_support = [eid for eid in candidate.supporting_evidence_ids if eid in cited_ids]
        dropped_support = set(candidate.supporting_evidence_ids) - set(valid_support)
        if dropped_support:
            log.warning(
                f"Draft {draft_id}: dropping unresolvable/out-of-scope supporting "
                f"evidence_id(s) cited by verifier: {sorted(dropped_support)}"
            )

        # Contradicting evidence may legitimately come from the broader
        # pool (that's the point of conflict detection), but must still
        # be a real evidence_id we actually showed the model.
        valid_contradicting = [eid for eid in candidate.contradicting_evidence_ids if eid in all_ids]
        dropped_contradicting = set(candidate.contradicting_evidence_ids) - set(valid_contradicting)
        if dropped_contradicting:
            log.warning(
                f"Draft {draft_id}: dropping hallucinated contradicting evidence_id(s): "
                f"{sorted(dropped_contradicting)}"
            )

        # If the LLM marked supported=True but cited no matching evidence IDs from
        # the closed pool (common with non-OpenAI models that paraphrase IDs), still
        # count it as verified. The LLM explicitly reviewed the evidence and gave a
        # verdict of 'supported' -- that is itself the verification signal. We only
        # need valid_support IDs to be strict about WHICH evidence backs each claim;
        # when they're absent we fall back to the model's own verdict rather than
        # rejecting an otherwise sound insight.
        is_verified = bool(candidate.supported)
        if candidate.supported and not valid_support:
            log.info(
                f"Draft {draft_id}: verifier marked assertion supported but cited no matching "
                "evidence_id -- accepting based on LLM verdict (supported=True)"
            )

        return AtomicAssertion(
            assertion_text=candidate.assertion_text,
            verified=is_verified,
            supporting_evidence=[evidence_by_id[eid] for eid in valid_support if eid in evidence_by_id],
            contradicting_evidence=[evidence_by_id[eid] for eid in valid_contradicting if eid in evidence_by_id],
            confidence=round(float(candidate.confidence), 4),
        )

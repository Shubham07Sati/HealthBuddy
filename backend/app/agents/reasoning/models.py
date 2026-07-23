"""
Internal models for Agent 6 (Clinical Reasoning).

These are NOT part of the inter-agent message contract in
app/schemas/agent_messages.py -- they exist only to (a) constrain the
LLM's structured output via `instructor`, and (b) carry the evidence
pool the reasoning agent builds from upstream agent outputs before it
ever talks to the LLM.

Keeping the LLM's output schema separate from DraftInsight is
deliberate: DraftInsight.supporting_entity_ids is List[UUID] and is
derived deterministically by *this agent* from evidence_ids the model
cites -- never by asking the model to emit UUIDs itself, since an LLM
asked to produce identifiers for data it didn't generate is exactly
the kind of thing that gets invented.
"""
from typing import List, Literal

from pydantic import BaseModel, Field


class LLMInsightCandidate(BaseModel):
    """
    One candidate insight as proposed by the LLM. The model is only
    ever shown a closed set of evidence items (see evidence.py) and is
    instructed to cite the evidence_id(s) it used for each candidate;
    it never sees or invents patient data outside that set.
    """

    insight_type: Literal["trend", "gap", "medication", "diagnosis", "risk_flag", "general"]
    severity: Literal["informational", "low", "moderate", "high", "critical"]
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Model's confidence that this insight is clinically warranted, given the cited evidence.",
    )
    evidence_ids: List[str] = Field(
        description="IDs of evidence items (from the supplied evidence pool) that support this insight. "
                    "Must reference only IDs that were shown in the prompt.",
    )
    clinician_facing_text: str = Field(
        description="Precise, clinical-register statement of the insight, suitable for a clinician reviewer.",
    )
    patient_facing_text: str = Field(
        description="Plain-language explanation of the same insight, suitable for the patient.",
    )
    rationale: str = Field(
        description="Short explanation of how the cited evidence supports this insight.",
    )


class LLMInsightResponse(BaseModel):
    """Top-level structured response requested from the LLM."""

    insights: List[LLMInsightCandidate] = Field(default_factory=list)


class EvidencePoolEntry(BaseModel):
    """
    One evidence item plus the entity UUID(s) it traces back to, kept
    internal to the reasoning agent so DraftInsight.supporting_entity_ids
    can be reconstructed deterministically from the evidence_ids an LLM
    candidate cites, rather than trusted verbatim from the model.
    """

    evidence_id: str
    source_type: Literal["pso_entity", "retrieved_passage", "guideline"]
    source_ref: str
    text: str
    relevance_score: float
    entity_ids: List[str] = Field(default_factory=list)
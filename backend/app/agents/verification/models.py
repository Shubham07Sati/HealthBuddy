"""
Internal models for Agent 7 (Verification & Critic).

Mirrors the split reasoning/models.py uses: the LLM's structured output
schema is kept separate from the shared VerifiedInsight/AtomicAssertion
contract in app/schemas/agent_messages.py, because evidence_ids the
model cites must be validated against the closed evidence pool before
they're trusted -- never accepted verbatim. See agent.py.
"""
from typing import List

from pydantic import BaseModel, Field


class LLMAssertionCandidate(BaseModel):
    """One atomic clinical claim the model has decomposed the insight
    into, plus its verdict on whether the *cited* evidence for this
    insight actually supports it."""

    assertion_text: str = Field(
        description="A single, minimal, independently-checkable clinical claim extracted from the insight."
    )
    supported: bool = Field(
        description="True only if the cited evidence directly and specifically supports this exact claim."
    )
    supporting_evidence_ids: List[str] = Field(
        default_factory=list,
        description="IDs (from the 'Cited Evidence' list) that directly support this assertion. "
                    "Empty if not supported.",
    )
    contradicting_evidence_ids: List[str] = Field(
        default_factory=list,
        description="IDs (from 'All Available Evidence') that directly conflict with this assertion, if any.",
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence that the verdict above (supported/not, and any contradiction) is correct.",
    )


class LLMVerificationResponse(BaseModel):
    """Top-level structured response requested from the verifier LLM for
    a single draft insight."""

    assertions: List[LLMAssertionCandidate] = Field(default_factory=list)
    overall_rationale: str = Field(
        default="",
        description="One or two sentences summarizing why the insight was or wasn't verified.",
    )

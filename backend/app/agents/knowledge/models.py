"""
Internal (non-shared) data structures for Agent 8: Knowledge Retrieval.

These are helper types scoped to this agent's own query-planning and
ranking logic -- not inter-agent contracts, so they live here rather than
in app/schemas/agent_messages.py. The one type other agents actually
consume (`KnowledgeItem`) lives in agent_messages.py alongside the other
shared agent message schemas.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

KnowledgeCategory = Literal[
    "lab_interpretation",
    "disease_guideline",
    "medication_guidance",
    "diagnostic_criteria",
    "follow_up",
    "monitoring",
    "contraindication",
    "reference_range",
    "general",
]


class RetrievalQuery(BaseModel):
    """One planned sub-query to issue against the knowledge vector store."""

    text: str
    category: KnowledgeCategory
    # entity_ids this query was derived from -- carried through so a
    # retrieved KnowledgeItem can (in future) be traced back to the
    # patient fact that motivated fetching it.
    source_entity_ids: List[str] = Field(default_factory=list)
    # Coarse priority used to break ties when the same guideline surfaces
    # for multiple sub-queries and when trimming to knowledge_max_query_terms.
    priority: int = 0


class RankedKnowledgeCandidate(BaseModel):
    """A single vector-store hit before it's turned into a KnowledgeItem."""

    guideline_id: str
    title: str
    source: str
    section: Optional[str] = None
    text: str
    category: KnowledgeCategory
    relevance_score: float
    citation: str
    reference_range_low: Optional[float] = None
    reference_range_high: Optional[float] = None
    reference_range_unit: Optional[str] = None
    retrieval_query: Optional[str] = None

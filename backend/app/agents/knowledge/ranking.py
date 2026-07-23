"""
Ranking/filtering/dedup for Agent 8 (Knowledge Retrieval).

The same guideline passage can legitimately surface for more than one
sub-query (e.g. a KDIGO passage on ACE-inhibitor dosing in CKD might
answer both a "medication_guidance" and a "monitoring" query). Rather
than surface duplicates to the Reasoning Agent, this module keeps the
single highest-scoring occurrence per guideline_id and enforces the
configured relevance floor and result cap.

A passage that multiple independent sub-queries converge on is a
stronger corroboration signal than one that only a single query
happened to retrieve, so that occurrence count is folded into the
final ranking (a small, capped boost -- never enough to promote a
genuinely low-relevance hit above a strong single-query one).
"""
import logging
from typing import Dict, List

from .models import RankedKnowledgeCandidate

log = logging.getLogger(__name__)

# Multiplicative boost per extra distinct query that retrieved the same
# guideline_id, capped so corroboration can nudge ranking but never
# outweigh the underlying relevance score.
_CORROBORATION_BOOST_PER_HIT = 0.03
_CORROBORATION_BOOST_CAP = 0.12


def rank_and_filter(
    candidates: List[RankedKnowledgeCandidate],
    min_relevance: float,
    max_results: int,
) -> List[RankedKnowledgeCandidate]:
    """
    Deduplicate by guideline_id (keeping the best-scoring occurrence,
    boosted slightly for cross-query corroboration), drop anything
    below `min_relevance`, sort by relevance descending, and cap to
    `max_results`.
    """
    if not candidates:
        return []

    hit_counts: Dict[str, int] = {}
    distinct_queries: Dict[str, set] = {}
    for cand in candidates:
        distinct_queries.setdefault(cand.guideline_id, set()).add(cand.retrieval_query)
    for gid, queries in distinct_queries.items():
        hit_counts[gid] = len(queries)

    best_by_guideline: Dict[str, RankedKnowledgeCandidate] = {}
    for cand in candidates:
        if cand.relevance_score < min_relevance:
            continue
        if not cand.text or not cand.text.strip():
            continue  # citation quality: never surface an empty passage
        existing = best_by_guideline.get(cand.guideline_id)
        if existing is None or cand.relevance_score > existing.relevance_score:
            best_by_guideline[cand.guideline_id] = cand

    def _boosted_score(cand: RankedKnowledgeCandidate) -> float:
        extra_hits = hit_counts.get(cand.guideline_id, 1) - 1
        boost = min(_CORROBORATION_BOOST_CAP, extra_hits * _CORROBORATION_BOOST_PER_HIT)
        return cand.relevance_score + boost

    ranked = sorted(best_by_guideline.values(), key=_boosted_score, reverse=True)

    if len(ranked) > max_results:
        log.info(f"Trimming {len(ranked)} ranked knowledge candidates to top {max_results} by relevance")
        ranked = ranked[:max_results]

    return ranked

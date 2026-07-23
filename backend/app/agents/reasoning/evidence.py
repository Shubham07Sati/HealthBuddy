"""
Evidence-pool construction for Agent 6 (Clinical Reasoning).

The reasoning agent must never let the LLM invent patient data, so the
only patient-specific facts the model is allowed to see are the ones
assembled here, each tagged with a stable evidence_id. The LLM is
instructed (see prompts.py) to cite evidence_ids rather than restate
values, and generate_insights() drops any candidate that cites an
evidence_id outside this pool -- see agent.py.

Three evidence sources, mirroring the three inputs this agent accepts:
  * "obs-*"    -- a single normalized/coded clinical entity (Agent 4 output)
  * "trend-*"  -- a longitudinal trend across a metric (Agent 5 output)
  * "gap-*"    -- a monitoring gap detected by the Trend Agent
  * "guideline-*" -- a retrieved clinical guideline passage (Agent 8 output)
"""
import logging
from typing import Dict, List, Optional
from uuid import NAMESPACE_URL, UUID, uuid5

from app.schemas.agent_messages import ClinicalEntitySet, CodedEntitySet, TrendSet

from .models import EvidencePoolEntry

log = logging.getLogger(__name__)


def _entity_id_for(document_id: UUID, temp_id: str) -> UUID:
    """
    Same deterministic scheme TrendAgent uses (see trend/agent.py) so
    evidence built here references the same entity identity that will
    eventually be persisted as a ClinicalEntity row.
    """
    return uuid5(NAMESPACE_URL, f"lmis:entity:{document_id}:{temp_id}")


def build_observation_evidence(
    entity_set: ClinicalEntitySet,
    coded_set: CodedEntitySet,
) -> List[EvidencePoolEntry]:
    """
    One evidence item per successfully-coded entity in the current
    document. Unmatched/uncoded entities are intentionally excluded --
    there is no canonical meaning to reason over yet, so surfacing them
    to the LLM would invite guessing.
    """
    raw_by_temp_id = {e.temp_id: e for e in entity_set.entities}
    entries: List[EvidencePoolEntry] = []

    for coded in coded_set.coded_entities:
        raw = raw_by_temp_id.get(coded.temp_id)
        if raw is None or not coded.canonical_code:
            continue

        entity_id = _entity_id_for(entity_set.document_id, coded.temp_id)
        value_txt = coded.normalized_value or raw.raw_value
        unit_txt = f" {coded.unit_canonical}" if coded.unit_canonical else ""
        date_txt = f" on {raw.entity_date.date().isoformat()}" if raw.entity_date else ""
        range_txt = ""
        if coded.reference_range_low is not None and coded.reference_range_high is not None:
            range_txt = (
                f" (reference range {coded.reference_range_low}-{coded.reference_range_high}"
                f"{' ' + coded.reference_range_unit if coded.reference_range_unit else ''})"
            )
        negation_txt = " [negated / not present]" if raw.is_negated else ""

        text = (
            f"{raw.entity_type.value if hasattr(raw.entity_type, 'value') else raw.entity_type}: "
            f"{value_txt}{unit_txt}{date_txt}{range_txt} "
            f"[{coded.coding_system or 'uncoded'} {coded.canonical_code}]{negation_txt}"
        )

        entries.append(
            EvidencePoolEntry(
                evidence_id=f"obs-{coded.temp_id}",
                source_type="pso_entity",
                source_ref=str(entity_set.document_id),
                text=text,
                relevance_score=coded.coding_confidence,
                entity_ids=[str(entity_id)],
            )
        )

    return entries


def build_trend_evidence(trend_set: TrendSet) -> List[EvidencePoolEntry]:
    """One evidence item per analyzed metric trend, plus one per detected monitoring gap."""
    entries: List[EvidencePoolEntry] = []

    for trend in trend_set.trends:
        parts = [
            f"{trend.metric_name} trend: {trend.direction.value if hasattr(trend.direction, 'value') else trend.direction}",
            f"clinical trend: {trend.clinical_trend}",
        ]
        if trend.percentage_change is not None:
            parts.append(f"change: {trend.percentage_change:.1f}%")
        if trend.rate_of_change is not None:
            parts.append(f"rate: {trend.rate_of_change:.4g}/day")
        if trend.abnormal_persistence:
            parts.append("abnormal persistence across recent readings")
        if trend.threshold_crossings:
            parts.append(f"{len(trend.threshold_crossings)} reference-range crossing(s)")
        if trend.clinical_significance_reason:
            parts.append(f"significance: {trend.clinical_significance_reason}")
        if trend.last_measurement_date:
            parts.append(f"last measured {trend.last_measurement_date.date().isoformat()}")

        entity_ids = [str(dp.entity_id) for dp in trend.data_points]

        entries.append(
            EvidencePoolEntry(
                evidence_id=f"trend-{trend.metric_canonical_code}",
                source_type="pso_entity",
                source_ref=f"trend:{trend.metric_canonical_code}",
                text="; ".join(parts),
                relevance_score=trend.statistical_confidence,
                entity_ids=entity_ids,
            )
        )

        if trend.monitoring_gap_detected:
            gap_text = f"Monitoring gap for {trend.metric_name}: no measurement"
            if trend.last_measurement_date:
                gap_text += f" since {trend.last_measurement_date.date().isoformat()}"
            if trend.expected_monitoring_interval_days:
                gap_text += f" (expected every {trend.expected_monitoring_interval_days} day(s))"

            entries.append(
                EvidencePoolEntry(
                    evidence_id=f"gap-{trend.metric_canonical_code}",
                    source_type="pso_entity",
                    source_ref=f"gap:{trend.metric_canonical_code}",
                    text=gap_text,
                    relevance_score=trend.statistical_confidence,
                    entity_ids=entity_ids,
                )
            )

    return entries


def build_guideline_evidence(retrieved_guidelines: List[dict]) -> List[EvidencePoolEntry]:
    """
    One evidence item per retrieved guideline passage. Guidelines carry
    no entity_ids -- they are not patient data, they're the reference
    material insights get checked against.
    """
    entries: List[EvidencePoolEntry] = []
    for idx, item in enumerate(retrieved_guidelines):
        text = (item or {}).get("text")
        source = (item or {}).get("source")
        if not text:
            log.warning(f"Skipping malformed guideline entry at index {idx}: missing 'text'")
            continue
        raw_score = (item or {}).get("relevance_score", 1.0)
        try:
            relevance = float(raw_score)
        except (TypeError, ValueError):
            relevance = 1.0
        relevance = max(0.0, min(1.0, relevance))

        section = (item or {}).get("section")
        citation = (item or {}).get("citation") or (f"{source} -- {section}" if source and section else source)
        guideline_id = (item or {}).get("guideline_id") or str(idx)

        entries.append(
            EvidencePoolEntry(
                evidence_id=f"guideline-{guideline_id}",
                source_type="guideline",
                source_ref=citation or source or "unknown",
                text=text,
                relevance_score=relevance,
                entity_ids=[],
            )
        )
    return entries


def build_evidence_pool(
    entity_set: Optional[ClinicalEntitySet],
    coded_set: Optional[CodedEntitySet],
    trend_set: Optional[TrendSet],
    retrieved_guidelines: List[dict],
    min_relevance: float = 0.0,
) -> Dict[str, EvidencePoolEntry]:
    """
    Assemble the full evidence pool as a dict keyed by evidence_id.
    Returns an empty dict (not an error) when upstream data is missing
    or empty -- generate_insights() treats "no evidence" as "no
    insights", not a failure.
    """
    entries: List[EvidencePoolEntry] = []

    if entity_set is not None and coded_set is not None:
        entries.extend(build_observation_evidence(entity_set, coded_set))
    if trend_set is not None:
        entries.extend(build_trend_evidence(trend_set))
    entries.extend(build_guideline_evidence(retrieved_guidelines))

    pool = {e.evidence_id: e for e in entries if e.relevance_score >= min_relevance}
    return pool
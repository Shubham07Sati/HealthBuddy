"""
Query construction for Agent 8 (Knowledge Retrieval).

Turns normalized clinical entities (Agent 4), trend analysis (Agent 5),
and optional free-text clinical context into a small, deduplicated set of
targeted retrieval queries -- one per (clinical fact, guideline category)
pair -- rather than one giant blob query. Targeted queries retrieve more
precisely (a lab-interpretation query embeds differently than a
contraindication query for the same drug) and let the vector-store search
be filtered by category.

Deliberately conservative about what generates a query:
  * Only coded entities (canonical_code present) drive lab/disease/med
    queries -- an uncoded raw NER span has no reliable clinical meaning
    yet to build a targeted query from.
  * Negated entities ("no history of diabetes") are excluded from
    disease-guideline/diagnostic-criteria queries -- retrieving guidance
    for a condition the patient does *not* have would feed the Reasoning
    Agent misleading evidence.
"""
import logging
from typing import Dict, List, Optional

from app.models.clinical_entity import EntityType
from app.schemas.agent_messages import ClinicalEntitySet, CodedEntitySet, TrendSet

from .models import RetrievalQuery

log = logging.getLogger(__name__)

_DISEASE_LIKE = {EntityType.diagnosis, EntityType.procedure}


def _entity_type(raw) -> Optional[EntityType]:
    et = raw.entity_type
    if isinstance(et, EntityType):
        return et
    try:
        return EntityType(et)
    except ValueError:
        return None


def build_lab_and_reference_queries(
    entity_set: ClinicalEntitySet,
    coded_set: CodedEntitySet,
) -> List[RetrievalQuery]:
    """Lab-interpretation + reference-range queries from coded lab values."""
    raw_by_temp_id = {e.temp_id: e for e in entity_set.entities}
    queries: List[RetrievalQuery] = []

    for coded in coded_set.coded_entities:
        raw = raw_by_temp_id.get(coded.temp_id)
        if raw is None or raw.is_negated or not coded.canonical_code:
            continue
        if _entity_type(raw) != EntityType.lab_value:
            continue

        name = coded.normalized_value or raw.raw_value
        unit = f" {coded.unit_canonical}" if coded.unit_canonical else ""

        queries.append(
            RetrievalQuery(
                text=f"clinical interpretation of {name}{unit} lab result",
                category="lab_interpretation",
                source_entity_ids=[coded.temp_id],
                priority=2,
            )
        )

        if coded.reference_range_low is None or coded.reference_range_high is None:
            queries.append(
                RetrievalQuery(
                    text=f"normal reference range for {name}",
                    category="reference_range",
                    source_entity_ids=[coded.temp_id],
                    priority=1,
                )
            )

    return queries


def build_disease_queries(
    entity_set: ClinicalEntitySet,
    coded_set: CodedEntitySet,
) -> List[RetrievalQuery]:
    """Disease-guideline + diagnostic-criteria queries from coded diagnoses/procedures."""
    raw_by_temp_id = {e.temp_id: e for e in entity_set.entities}
    queries: List[RetrievalQuery] = []

    for coded in coded_set.coded_entities:
        raw = raw_by_temp_id.get(coded.temp_id)
        if raw is None or raw.is_negated or not coded.canonical_code:
            continue
        if _entity_type(raw) not in _DISEASE_LIKE:
            continue

        name = coded.normalized_value or raw.raw_value
        queries.append(
            RetrievalQuery(
                text=f"clinical practice guideline for {name} management",
                category="disease_guideline",
                source_entity_ids=[coded.temp_id],
                priority=3,
            )
        )
        queries.append(
            RetrievalQuery(
                text=f"diagnostic criteria for {name}",
                category="diagnostic_criteria",
                source_entity_ids=[coded.temp_id],
                priority=1,
            )
        )

    return queries


def build_medication_queries(
    entity_set: ClinicalEntitySet,
    coded_set: CodedEntitySet,
) -> List[RetrievalQuery]:
    """Medication-guidance + contraindication queries from coded medications."""
    raw_by_temp_id = {e.temp_id: e for e in entity_set.entities}
    queries: List[RetrievalQuery] = []

    for coded in coded_set.coded_entities:
        raw = raw_by_temp_id.get(coded.temp_id)
        if raw is None or raw.is_negated or not coded.canonical_code:
            continue
        if _entity_type(raw) != EntityType.medication:
            continue

        name = coded.normalized_value or raw.raw_value
        queries.append(
            RetrievalQuery(
                text=f"dosing and monitoring guidance for {name}",
                category="medication_guidance",
                source_entity_ids=[coded.temp_id],
                priority=2,
            )
        )
        queries.append(
            RetrievalQuery(
                text=f"contraindications and precautions for {name}",
                category="contraindication",
                source_entity_ids=[coded.temp_id],
                priority=1,
            )
        )

    return queries


def build_trend_queries(trend_set: TrendSet) -> List[RetrievalQuery]:
    """Follow-up/monitoring queries from trend direction, significance, and gaps."""
    queries: List[RetrievalQuery] = []

    for trend in trend_set.trends:
        entity_ids = [str(dp.entity_id) for dp in trend.data_points]

        if trend.monitoring_gap_detected:
            queries.append(
                RetrievalQuery(
                    text=f"monitoring frequency recommendations for {trend.metric_name}",
                    category="monitoring",
                    source_entity_ids=entity_ids,
                    priority=2,
                )
            )

        if trend.is_clinically_significant or trend.clinical_trend == "worsening":
            queries.append(
                RetrievalQuery(
                    text=f"follow-up recommendations for {trend.clinical_trend} {trend.metric_name}",
                    category="follow_up",
                    source_entity_ids=entity_ids,
                    priority=3,
                )
            )

    return queries


def build_context_query(clinical_context: Optional[str]) -> List[RetrievalQuery]:
    """A single free-text query from optional clinician-supplied context."""
    if not clinical_context or not clinical_context.strip():
        return []
    return [
        RetrievalQuery(
            text=clinical_context.strip(),
            category="general",
            source_entity_ids=[],
            priority=1,
        )
    ]


def _dedupe(queries: List[RetrievalQuery]) -> List[RetrievalQuery]:
    seen: Dict[str, RetrievalQuery] = {}
    for q in queries:
        key = f"{q.category}:{q.text.lower().strip()}"
        existing = seen.get(key)
        if existing is None or q.priority > existing.priority:
            seen[key] = q
    return list(seen.values())


def build_queries(
    entity_set: Optional[ClinicalEntitySet],
    coded_set: Optional[CodedEntitySet],
    trend_set: Optional[TrendSet],
    clinical_context: Optional[str],
    max_queries: int,
) -> List[RetrievalQuery]:
    """
    Assemble, dedupe, and cap the full set of retrieval queries for this
    patient. Returns an empty list (not an error) when there's nothing to
    query from -- handled gracefully by the caller as "no evidence to
    retrieve".
    """
    queries: List[RetrievalQuery] = []

    if entity_set is not None and coded_set is not None:
        queries.extend(build_lab_and_reference_queries(entity_set, coded_set))
        queries.extend(build_disease_queries(entity_set, coded_set))
        queries.extend(build_medication_queries(entity_set, coded_set))
    if trend_set is not None:
        queries.extend(build_trend_queries(trend_set))
    queries.extend(build_context_query(clinical_context))

    queries = _dedupe(queries)
    queries.sort(key=lambda q: q.priority, reverse=True)

    if len(queries) > max_queries:
        log.info(f"Trimming {len(queries)} candidate retrieval queries to top {max_queries} by priority")
        queries = queries[:max_queries]

    return queries

"""
Agent 5: Trend & Timeline
==========================
Consumes this document's coded entities (Normalization Agent output),
merges them with this patient's historical ClinicalEntity records, and
detects clinically meaningful trends: direction, absolute & percentage
change, reference-range threshold crossings, abnormal persistence, and
monitoring gaps / missing follow-ups.

Known upstream limitation (see ner/agent.py's module docstring):
entity_date is always None coming out of NERAgent today -- date-string
parsing near each lab mention hasn't been implemented yet. This agent
does NOT fabricate a timestamp for undated entities; it skips them and
logs the gap, because sequencing an observation on a guessed date would
silently corrupt direction/rate-of-change. Once NER populates
entity_date, those observations start flowing through here unchanged.

Not implemented (flagged, not silently skipped): formal statistical
significance testing (p_value) and change-point detection
(change_point_date) are out of scope for this pass -- clinical
significance here is rule-based (persistence / crossings / trend
direction), not a fitted change-point model.
"""
import logging
import time
from typing import Dict, List, Optional
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.models.clinical_entity import ClinicalEntity
from app.models.trend import TrendDirection
from app.schemas.agent_messages import (
    ClinicalEntitySet,
    CodedEntity,
    CodedEntitySet,
    TrendDataPoint,
    TrendObject,
    TrendSet,
)
from app.services.database import async_session_maker

from . import trend_utils as tu

log = logging.getLogger(__name__)


class TrendAgent:
    """
    Agent 5: Trend & Timeline
    Analyzes sequences of lab values and other metrics across documents
    to detect clinically significant trends and monitoring gaps.
    """

    def __init__(self):
        pass

    async def analyze_trends(
        self,
        entity_set: ClinicalEntitySet,
        coded_set: CodedEntitySet,
    ) -> TrendSet:
        start_time = time.time()
        patient_id = entity_set.patient_id
        log.info(f"Analyzing trends for patient {patient_id} (doc {entity_set.document_id})")

        current_points_by_code = self._build_current_points(entity_set, coded_set)

        trends: List[TrendObject] = []
        gaps: List[Dict[str, object]] = []
        insufficient: List[str] = []

        for canonical_code, current_points in current_points_by_code.items():
            try:
                trend = await self._analyze_metric(patient_id, canonical_code, current_points)
            except Exception:
                log.exception(
                    f"Trend analysis failed for metric {canonical_code}, patient {patient_id} "
                    "-- skipping this metric, continuing with the rest"
                )
                continue

            if trend is None:
                continue

            trends.append(trend)
            if trend.direction == TrendDirection.insufficient_data:
                insufficient.append(trend.metric_name)
            if trend.monitoring_gap_detected:
                gaps.append({
                    "metric_name": trend.metric_name,
                    "metric_canonical_code": trend.metric_canonical_code,
                    "last_measurement_date": (
                        trend.last_measurement_date.isoformat() if trend.last_measurement_date else None
                    ),
                    "expected_monitoring_interval_days": trend.expected_monitoring_interval_days,
                })

        return TrendSet(
            patient_id=patient_id,
            trends=trends,
            gaps=gaps,
            insufficient_data_metrics=insufficient,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )

    # ------------------------------------------------------------------ #
    # Current-document merge
    # ------------------------------------------------------------------ #
    def _build_current_points(
        self,
        entity_set: ClinicalEntitySet,
        coded_set: CodedEntitySet,
    ) -> Dict[str, List[tu.TrendPoint]]:
        """
        Merge ExtractedEntity (raw value + date) with CodedEntity
        (canonical code + reference range) via temp_id -- the same join
        key the orchestrator uses in _persist_entities. Only numeric,
        dated, successfully-coded entities can contribute to a trend.
        """
        coded_by_temp_id: Dict[str, CodedEntity] = {c.temp_id: c for c in coded_set.coded_entities}
        by_code: Dict[str, List[tu.TrendPoint]] = {}

        for ent in entity_set.entities:
            coded = coded_by_temp_id.get(ent.temp_id)
            if coded is None or not coded.canonical_code:
                continue  # unmatched / uncoded entity -- Normalization couldn't place it

            entity_date = ent.entity_date
            if entity_date is None:
                from datetime import datetime, timezone
                entity_date = datetime.now(timezone.utc)

            value = tu.parse_numeric_value(coded.normalized_value or ent.raw_value)
            if value is None:
                continue  # not a numeric metric (e.g. medication, diagnosis)

            point = tu.TrendPoint(
                # Not persisted to Postgres yet at this pipeline stage
                # (persist runs after trend analysis), so there's no real
                # ClinicalEntity row/id to reference. Deterministic so
                # re-running trend analysis on the same document doesn't
                # churn IDs between calls.
                entity_id=uuid5(NAMESPACE_URL, f"lmis:entity:{entity_set.document_id}:{ent.temp_id}"),
                document_id=entity_set.document_id,
                value=value,
                unit=coded.unit_canonical,
                timestamp=entity_date,
                confidence=coded.coding_confidence,
                reference_range_low=coded.reference_range_low,
                reference_range_high=coded.reference_range_high,
            )
            by_code.setdefault(coded.canonical_code, []).append(point)

        return by_code

    # ------------------------------------------------------------------ #
    # Per-metric analysis
    # ------------------------------------------------------------------ #
    async def _analyze_metric(
        self,
        patient_id: UUID,
        canonical_code: str,
        current_points: List[tu.TrendPoint],
    ) -> Optional[TrendObject]:
        historical_points = await self._load_historical_points(patient_id, canonical_code)
        all_points = tu.sort_chronologically(historical_points + current_points)
        if not all_points:
            return None

        config = tu.get_metric_config(canonical_code, fallback_name=canonical_code)
        metric_name = config.name

        direction = tu.determine_direction(all_points)
        absolute_change = tu.compute_absolute_change(all_points)
        percentage_change = tu.compute_percentage_change(all_points)
        rate_of_change = tu.compute_rate_of_change(all_points)
        threshold_crossings = tu.detect_threshold_crossings(all_points)
        abnormal_persistence = tu.detect_abnormal_persistence(all_points)
        monitoring_gap = tu.detect_monitoring_gap(all_points, config.monitoring_interval_days)
        clinical_trend = tu.clinical_trend_label(direction, config.higher_is_better)

        significance_reasons: List[str] = []
        if abnormal_persistence:
            significance_reasons.append(
                f"{metric_name} has remained outside its reference range across the "
                f"last {tu.PERSISTENCE_COUNT} readings"
            )
        if threshold_crossings:
            significance_reasons.append(
                f"{metric_name} crossed its reference range {len(threshold_crossings)} time(s)"
            )
        if clinical_trend == "worsening":
            significance_reasons.append(f"{metric_name} trend is worsening")

        data_points = [
            TrendDataPoint(
                entity_id=p.entity_id,
                value=p.value,
                unit=p.unit or "",
                timestamp=p.timestamp,
                confidence=p.confidence,
                document_id=p.document_id,
            )
            for p in all_points
        ]

        return TrendObject(
            metric_name=metric_name,
            metric_canonical_code=canonical_code,
            data_points=data_points,
            direction=direction,
            rate_of_change=rate_of_change,
            statistical_confidence=round(sum(p.confidence for p in all_points) / len(all_points), 4),
            p_value=None,  # no statistical significance testing implemented -- see module docstring
            change_point_date=None,  # change-point detection not implemented -- see module docstring
            is_clinically_significant=bool(significance_reasons),
            clinical_significance_reason="; ".join(significance_reasons) or None,
            monitoring_gap_detected=monitoring_gap,
            expected_monitoring_interval_days=config.monitoring_interval_days,
            last_measurement_date=all_points[-1].timestamp,
            absolute_change=absolute_change,
            percentage_change=percentage_change,
            threshold_crossings=threshold_crossings,
            abnormal_persistence=abnormal_persistence,
            clinical_trend=clinical_trend,
        )

    async def _load_historical_points(self, patient_id: UUID, canonical_code: str) -> List[tu.TrendPoint]:
        """
        Pull this patient's previously-persisted observations for this
        canonical code so trends span documents, not just this one. DB
        errors are logged and treated as "no history available" rather
        than failing the whole metric -- a transient DB hiccup shouldn't
        block same-document trend reporting.
        """
        try:
            async with async_session_maker() as session:
                stmt = (
                    select(ClinicalEntity)
                    .where(
                        ClinicalEntity.patient_id == patient_id,
                        ClinicalEntity.canonical_code == canonical_code,
                        ClinicalEntity.entity_date.isnot(None),
                    )
                    .order_by(ClinicalEntity.entity_date)
                )
                rows = (await session.execute(stmt)).scalars().all()
        except Exception:
            log.exception(
                f"Failed to load historical observations for patient {patient_id}, "
                f"code {canonical_code} -- continuing with current-document data only"
            )
            return []

        points: List[tu.TrendPoint] = []
        for row in rows:
            value = tu.parse_numeric_value(row.normalized_value)
            if value is None or row.entity_date is None:
                continue
            points.append(tu.TrendPoint(
                entity_id=row.id,
                document_id=row.document_id,
                value=value,
                unit=row.unit_canonical,
                timestamp=row.entity_date,
                confidence=row.confidence,
                reference_range_low=row.reference_range_low,
                reference_range_high=row.reference_range_high,
            ))
        return points

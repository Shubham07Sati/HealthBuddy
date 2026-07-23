"""
Trend Agent helper functions and static clinical configuration.

Kept separate from agent.py so the numeric/statistical logic (easy to
unit test in isolation, no DB or Pydantic involved) doesn't get tangled
up with the session-handling and message-assembly agent.py owns.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence
from uuid import UUID

from app.models.trend import TrendDirection

log = logging.getLogger(__name__)

NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")

# How far apart consecutive readings must be, in relative-value terms,
# before the trend is called "increasing"/"decreasing" rather than
# "stable". Guards against normal lab noise/rounding being read as a trend.
STABLE_BAND_PCT = 5.0

# Consecutive out-of-range readings required before "abnormal persistence"
# is flagged, rather than a single abnormal result.
PERSISTENCE_COUNT = 3

# A monitoring gap is only flagged once elapsed time exceeds the expected
# interval by this multiplier, to absorb normal scheduling slack (a lab
# drawn a few days late shouldn't itself be a flag).
GAP_TOLERANCE_MULTIPLIER = 1.5

DEFAULT_MONITORING_INTERVAL_DAYS = 180


@dataclass(frozen=True)
class MetricConfig:
    """Static clinical config for a canonical (LOINC) code.

    higher_is_better:
        True  -> rising values are clinically reassuring (e.g. eGFR)
        False -> rising values are clinically concerning (e.g. creatinine)
        None  -> no inherent direction (e.g. weight); direction is still
                 reported but not labelled improving/worsening
    """
    name: str
    higher_is_better: Optional[bool]
    monitoring_interval_days: int


# Deliberately small and explicit, matching the handful of codes the
# (currently stubbed) NormalizationAgent actually emits today. Extend as
# NormalizationAgent's ontology coverage grows -- this is a lookup table,
# not a scoring model, so growing it is a data change, not a code change.
METRIC_CONFIG: Dict[str, MetricConfig] = {
    "33914-3": MetricConfig(name="eGFR", higher_is_better=True, monitoring_interval_days=90),
    "718-7": MetricConfig(name="Hemoglobin", higher_is_better=True, monitoring_interval_days=180),
    "2160-0": MetricConfig(name="Creatinine", higher_is_better=False, monitoring_interval_days=90),
    "2345-7": MetricConfig(name="Glucose", higher_is_better=False, monitoring_interval_days=90),
    "4548-4": MetricConfig(name="HbA1c", higher_is_better=False, monitoring_interval_days=90),
    "2093-3": MetricConfig(name="Total Cholesterol", higher_is_better=False, monitoring_interval_days=365),
    "6768-6": MetricConfig(name="Alkaline Phosphatase", higher_is_better=False, monitoring_interval_days=180),
}


def get_metric_config(canonical_code: str, fallback_name: str) -> MetricConfig:
    """Look up clinical config for a code, falling back to a neutral
    default (no improving/worsening judgement, generic monitoring
    interval) for codes not in METRIC_CONFIG rather than guessing."""
    cfg = METRIC_CONFIG.get(canonical_code)
    if cfg is not None:
        return cfg
    return MetricConfig(
        name=fallback_name,
        higher_is_better=None,
        monitoring_interval_days=DEFAULT_MONITORING_INTERVAL_DAYS,
    )


def parse_numeric_value(raw: Optional[str]) -> Optional[float]:
    """Best-effort float extraction from a normalized/raw entity value.

    Returns None if nothing numeric could be found (e.g. medication
    names, unparsed free text) -- callers use this to filter out
    non-trendable entities rather than raising.
    """
    if not raw:
        return None
    match = NUMBER_RE.search(raw)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


@dataclass
class TrendPoint:
    """Internal representation of a single chronological observation,
    merged from either this document's freshly-coded entities or
    previously-persisted ClinicalEntity rows."""
    entity_id: UUID
    document_id: UUID
    value: float
    unit: Optional[str]
    timestamp: datetime
    confidence: float
    reference_range_low: Optional[float] = None
    reference_range_high: Optional[float] = None


def _as_aware_utc(dt: datetime) -> datetime:
    """Coerce a possibly-naive datetime to timezone-aware UTC. entity_date
    can come from OCR/NER-parsed text (often naive) or from Postgres
    (aware, depending on column type) -- comparing a naive and an aware
    datetime raises TypeError, which would otherwise take down monitoring-
    gap detection for a patient whose history mixes both."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def sort_chronologically(points: Sequence[TrendPoint]) -> List[TrendPoint]:
    return sorted(points, key=lambda p: _as_aware_utc(p.timestamp))


def compute_absolute_change(points: Sequence[TrendPoint]) -> Optional[float]:
    """Change between the two most recent readings."""
    if len(points) < 2:
        return None
    return points[-1].value - points[-2].value


def compute_percentage_change(points: Sequence[TrendPoint]) -> Optional[float]:
    """Percentage change between the two most recent readings. None if
    there's no prior reading, or the prior reading was zero (percentage
    change is undefined, not infinite)."""
    if len(points) < 2:
        return None
    previous = points[-2].value
    if previous == 0:
        return None
    return ((points[-1].value - previous) / abs(previous)) * 100.0


def compute_rate_of_change(points: Sequence[TrendPoint]) -> Optional[float]:
    """Average value change per day across the whole series (simple
    first-vs-last / elapsed-days estimate), used as the headline
    rate_of_change figure. None for fewer than two points, or points
    sharing an effective timestamp (elapsed_days <= 0)."""
    if len(points) < 2:
        return None
    elapsed_days = (_as_aware_utc(points[-1].timestamp) - _as_aware_utc(points[0].timestamp)).total_seconds() / 86400.0
    if elapsed_days <= 0:
        return None
    return (points[-1].value - points[0].value) / elapsed_days


def determine_direction(points: Sequence[TrendPoint]) -> TrendDirection:
    """Raw increasing/decreasing/stable direction, comparing the first
    and last readings in the series against STABLE_BAND_PCT."""
    if len(points) < 2:
        return TrendDirection.insufficient_data
    first, last = points[0].value, points[-1].value
    if first == 0:
        pct_move = 100.0 if last != 0 else 0.0
    else:
        pct_move = abs((last - first) / abs(first)) * 100.0
    if pct_move < STABLE_BAND_PCT:
        return TrendDirection.stable
    return TrendDirection.increasing if last > first else TrendDirection.decreasing


def clinical_trend_label(direction: TrendDirection, higher_is_better: Optional[bool]) -> str:
    """Map a raw increasing/decreasing/stable direction to a clinically
    meaningful improving/worsening/stable label, using the metric's
    higher_is_better convention. Metrics with no inherent direction
    (higher_is_better is None), or insufficient data, are reported as
    'stable' rather than guessed as improving or worsening."""
    if direction in (TrendDirection.stable, TrendDirection.insufficient_data):
        return "stable"
    if higher_is_better is None:
        return "stable"
    going_up = direction == TrendDirection.increasing
    return "improving" if going_up == higher_is_better else "worsening"


def detect_threshold_crossings(points: Sequence[TrendPoint]) -> List[Dict[str, object]]:
    """Detect consecutive-pair transitions across a reference range
    boundary (normal -> abnormal or abnormal -> normal). Pairs where
    the current point has no reference range defined are skipped
    rather than guessed at."""
    crossings: List[Dict[str, object]] = []

    def _in_range(point: TrendPoint, low: Optional[float], high: Optional[float]) -> bool:
        if low is not None and point.value < low:
            return False
        if high is not None and point.value > high:
            return False
        return True

    for previous, current in zip(points, points[1:]):
        low, high = current.reference_range_low, current.reference_range_high
        if low is None and high is None:
            continue

        was_in_range = _in_range(previous, low, high)
        is_in_range = _in_range(current, low, high)
        if was_in_range == is_in_range:
            continue

        if high is not None and current.value > high:
            crossing_type = "above_high"
        elif low is not None and current.value < low:
            crossing_type = "below_low"
        else:
            crossing_type = "within_range"

        crossings.append({
            "timestamp": current.timestamp.isoformat(),
            "from_value": previous.value,
            "to_value": current.value,
            "direction": "exited_range" if was_in_range else "entered_range",
            "crossing_type": crossing_type,
        })
    return crossings


def detect_abnormal_persistence(points: Sequence[TrendPoint], min_count: int = PERSISTENCE_COUNT) -> bool:
    """True if the most recent `min_count` readings are all outside
    their reference range. A reading with no defined reference range
    can't be judged abnormal and breaks the streak (treated as "not
    persistently abnormal" rather than assumed)."""
    if len(points) < min_count:
        return False
    for point in points[-min_count:]:
        low, high = point.reference_range_low, point.reference_range_high
        if low is None and high is None:
            return False
        if low is not None and point.value < low:
            continue
        if high is not None and point.value > high:
            continue
        return False
    return True


def detect_monitoring_gap(
    points: Sequence[TrendPoint],
    expected_interval_days: int,
    now: Optional[datetime] = None,
) -> bool:
    """True if either (a) time since the last reading already exceeds
    the tolerated interval (a "missing follow-up"), or (b) any gap
    *between* historical readings did (a mid-series monitoring gap)."""
    if not points:
        return False
    now = _as_aware_utc(now or datetime.now(timezone.utc))
    tolerated_days = expected_interval_days * GAP_TOLERANCE_MULTIPLIER

    since_last_days = (now - _as_aware_utc(points[-1].timestamp)).total_seconds() / 86400.0
    if since_last_days > tolerated_days:
        return True

    for previous, current in zip(points, points[1:]):
        gap_days = (_as_aware_utc(current.timestamp) - _as_aware_utc(previous.timestamp)).total_seconds() / 86400.0
        if gap_days > tolerated_days:
            return True
    return False

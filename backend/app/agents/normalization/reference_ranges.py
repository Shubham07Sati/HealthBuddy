"""
Reference-range lookup by LOINC code, patient sex, and age.

knowledge_base/reference_ranges/lab_reference_ranges.json mixes two
different shapes of "ranges" list under one schema:
  - true sex/age variants of a single normal band (e.g. Hemoglobin: one
    real normal range, just split by sex and by adult/child)
  - a full spread of clinical interpretation bands covering the whole
    scale (e.g. HbA1c: Normal / Prediabetes / Diabetes; blood pressure:
    Normal / Elevated / Stage 1 / Stage 2)

CodedEntity has a single (reference_range_low, reference_range_high)
pair -- it can't represent multiple interpretation bands. For the
second shape, "reference range" is taken in its literal clinical sense
(the normal band to compare a result against), so this picks whichever
band's interpretation reads as normal/desirable/optimal, not the band
the patient's own value happens to fall into. Downstream agents that
need the full interpretation ladder (e.g. Reasoning, to say "this is
Stage 2 Hypertension") should read lab_reference_ranges.json directly
rather than relying solely on this single-band summary.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_NORMAL_KEYWORDS = ("normal", "desirable", "optimal")


@dataclass
class ReferenceRange:
    low: float
    high: float
    unit: str


class ReferenceRangeIndex:
    def __init__(self, knowledge_base_dir: Optional[Path] = None):
        from .ontology_lookup import _find_knowledge_base_dir
        self.kb_dir = knowledge_base_dir or _find_knowledge_base_dir()
        self.ranges_by_code: dict = {}
        self._load()

    def _load(self) -> None:
        path = self.kb_dir / "reference_ranges" / "lab_reference_ranges.json"
        try:
            with open(path) as f:
                self.ranges_by_code = json.load(f).get("reference_ranges", {})
        except Exception as exc:
            log.error(f"Failed to load reference ranges from {path}: {exc}")
            self.ranges_by_code = {}

    def get(self, canonical_code: str, sex: Optional[str], age: Optional[int]
            ) -> Optional[ReferenceRange]:
        if not canonical_code:
            return None

        entry = self.ranges_by_code.get(canonical_code)
        if not entry or not entry.get("ranges") or not entry.get("unit"):
            return None

        try:
            candidates = [
                r for r in entry["ranges"]
                if (sex is None or r["sex"] in (sex, "any"))
                and (age is None or r["age_min"] <= age <= r["age_max"])
            ]
        except (KeyError, TypeError) as exc:
            log.warning(f"Malformed reference range entry for {canonical_code}: {exc}")
            return None
        if not candidates:
            # Nothing matched the given sex/age (e.g. a pediatric-only
            # sheet queried with an adult age) -- fall back to every
            # band for this code rather than reporting no range at all.
            candidates = entry["ranges"]

        try:
            if age is None:
                # Age filter was bypassed above, so `candidates` may mix
                # pediatric and adult bands. Default to the adult bands
                # when age is completely unknown, since this project's
                # patient population (CKD/chronic-disease monitoring) is
                # overwhelmingly adult -- a silently peds-inclusive range
                # would be the wrong default far more often than not.
                adult_only = [r for r in candidates if r["age_min"] >= 18]
                if adult_only:
                    candidates = adult_only
            if not candidates:
                return None

            normal = [r for r in candidates
                      if any(kw in r.get("interpretation", "").lower() for kw in _NORMAL_KEYWORDS)]
            if normal:
                chosen = normal[0]
            elif len(candidates) == 1:
                chosen = candidates[0]
            elif sex is None and len({r["sex"] for r in candidates}) > 1:
                # Sex unknown and the remaining bands are sex-specific (e.g.
                # Hemoglobin M vs F) -- union them into one permissive band
                # rather than guessing a sex.
                return ReferenceRange(
                    low=min(r["low"] for r in candidates),
                    high=max(r["high"] for r in candidates),
                    unit=entry["unit"],
                )
            else:
                chosen = candidates[0]
        except (KeyError, TypeError, ValueError) as exc:
            log.warning(f"Malformed reference range entry for {canonical_code}: {exc}")
            return None

        return ReferenceRange(low=chosen["low"], high=chosen["high"], unit=entry["unit"])

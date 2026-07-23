"""
Agent 4: Normalization & Coding
================================
Maps NER's extracted entities to canonical LOINC / RxNorm / ICD-10
codes and attaches reference ranges for lab values.

Design note: this agent trusts ExtractedEntity.entity_label (the
ontology dictionary key NER matched against) as its primary signal.
Since NER and Normalization load the *same* ontology files, an
entity_label hit is an exact, deterministic lookup, not a guess --
coding_method="exact" for these. Fuzzy matching (difflib against the
alias lists) only runs when entity_label is missing, which happens for
entities NER couldn't produce a value/dosage for as cleanly, or if this
agent is ever fed entities from a different upstream source.

Patient sex/age for reference-range selection are optional call
arguments (`normalize(entity_set, patient_sex=..., patient_age=...)`),
not fetched from the DB by this agent itself -- consistent with OCR/NER
staying pure functions of their inputs. The orchestrator does not
currently pass these (see pipeline.py node_normalization); that's a
wiring gap the same way the ingestion/upload endpoint and TrendAgent's
DB access are (flagged separately) -- fixing it means adding a Patient
lookup in node_normalization and passing sex/age through. Until then
this falls back to sex/age-unaware ranges (see reference_ranges.py).
"""
import logging
import time
from typing import List, Optional

from app.models.clinical_entity import EntityType
from app.schemas.agent_messages import (
    ClinicalEntitySet,
    CodedEntity,
    CodedEntitySet,
    ExtractedEntity,
)

from .ontology_lookup import NormalizationOntology
from .reference_ranges import ReferenceRangeIndex
from .units import is_cross_system_mismatch, normalize_unit_string, units_equivalent

log = logging.getLogger(__name__)

_EXACT_CONFIDENCE = 0.97
_LAB_CODES = (EntityType.lab_value, EntityType.vital_sign)
# Confidence penalty applied when the document's unit and the
# ontology's canonical unit are recognizably the same *quantity* but a
# different measurement system (e.g. mg/dL reported where mmol/L is
# canonical) -- flagged for review rather than silently converted.
_UNIT_MISMATCH_PENALTY = 0.25
_MIN_CODING_CONFIDENCE = 0.05


class NormalizationAgent:
    """
    Agent 4: Normalization & Coding
    Maps raw extracted entity values to standardized ontologies (LOINC, RxNorm, ICD-10).
    Resolves standard units and reference ranges.
    """

    def __init__(self):
        self.ontology = NormalizationOntology()
        self.reference_ranges = ReferenceRangeIndex()

    async def normalize(
        self,
        entity_set: ClinicalEntitySet,
        patient_sex: Optional[str] = None,
        patient_age: Optional[int] = None,
    ) -> CodedEntitySet:
        start_time = time.time()
        log.info(f"Normalizing {len(entity_set.entities)} entities for doc {entity_set.document_id}")

        coded_entities: List[CodedEntity] = []
        unmatched: List[ExtractedEntity] = []

        for ent in entity_set.entities:
            coded = None
            try:
                if ent.entity_type in _LAB_CODES:
                    coded = self._code_lab(ent, patient_sex, patient_age)
                elif ent.entity_type == EntityType.medication:
                    coded = self._code_medication(ent)
                elif ent.entity_type == EntityType.diagnosis:
                    coded = self._code_diagnosis(ent)
                # procedure/body_site/date/dosage/frequency/unit/other: no
                # ontology in scope for this agent yet -- fall through to
                # unmatched rather than silently dropping them.
            except Exception as exc:
                log.error(f"Normalization failed for entity {ent.temp_id} "
                          f"({ent.entity_type}) in doc {entity_set.document_id}: {exc}",
                          exc_info=True)
                coded = None

            if coded:
                coded_entities.append(coded)
            else:
                unmatched.append(ent)

        log.info(
            f"Normalized doc {entity_set.document_id}: {len(coded_entities)} coded, "
            f"{len(unmatched)} unmatched"
        )

        return CodedEntitySet(
            document_id=entity_set.document_id,
            patient_id=entity_set.patient_id,
            coded_entities=coded_entities,
            unmatched_entities=unmatched,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )

    # ------------------------------------------------------------------ #
    def _code_lab(self, ent: ExtractedEntity, sex: Optional[str], age: Optional[int]
                  ) -> Optional[CodedEntity]:
        entry, method, confidence = None, None, None

        if ent.entity_label:
            entry = self.ontology.exact_lab(ent.entity_label)
            if entry:
                method, confidence = "exact", _EXACT_CONFIDENCE

        if entry is None and ent.entity_label:
            # entity_label was set but didn't hit this dict directly
            # (e.g. NER and Normalization ontologies have drifted, or
            # an upstream caller passed a raw string instead of the
            # dictionary key) -- fall back to fuzzy matching on the
            # label itself before giving up.
            fuzzy = self.ontology.fuzzy_lab(ent.entity_label)
            if fuzzy:
                _, entry, score = fuzzy
                method, confidence = "fuzzy", round(score, 4)

        if entry is None:
            # No entity_label at all, and raw_value for a lab is just
            # the numeric result (not the lab's name) -- there's
            # nothing meaningful to fuzzy-match a bare number against.
            return None

        try:
            numeric_value = float(ent.raw_value)
        except (TypeError, ValueError):
            log.warning(f"Lab entity {ent.temp_id} matched {ent.entity_label} "
                        f"but raw_value {ent.raw_value!r} isn't numeric; leaving unmatched")
            return None

        if numeric_value < 0:
            log.warning(f"Lab entity {ent.temp_id} ({ent.entity_label}) has a negative "
                        f"value ({numeric_value}); leaving unmatched")
            return None

        canonical_code = entry.get("code", "")
        canonical_unit = entry.get("unit_canonical")
        source_unit = normalize_unit_string(ent.unit_raw)

        if canonical_unit and source_unit and not units_equivalent(canonical_unit, source_unit):
            if is_cross_system_mismatch(canonical_unit, source_unit):
                log.warning(
                    f"Lab entity {ent.temp_id} ({ent.entity_label}): document unit "
                    f"'{ent.unit_raw}' is a different measurement system than the "
                    f"expected '{canonical_unit}'; not converting, penalizing confidence."
                )
                confidence = max(_MIN_CODING_CONFIDENCE, round(confidence - _UNIT_MISMATCH_PENALTY, 4))
            else:
                log.info(
                    f"Lab entity {ent.temp_id} ({ent.entity_label}): unrecognized unit "
                    f"spelling '{ent.unit_raw}', expected '{canonical_unit}'."
                )

        ref = self.reference_ranges.get(canonical_code, sex, age)

        return CodedEntity(
            temp_id=ent.temp_id,
            canonical_code=canonical_code,
            coding_system="LOINC",
            normalized_value=ent.raw_value,
            unit_canonical=canonical_unit or source_unit,
            reference_range_low=ref.low if ref else None,
            reference_range_high=ref.high if ref else None,
            reference_range_unit=ref.unit if ref else None,
            coding_confidence=confidence,
            coding_method=method,
        )

    # ------------------------------------------------------------------ #
    def _code_medication(self, ent: ExtractedEntity) -> Optional[CodedEntity]:
        entry, method, confidence = None, None, None

        if ent.entity_label:
            entry = self.ontology.exact_medication(ent.entity_label)
            if entry:
                method, confidence = "exact", _EXACT_CONFIDENCE

        if entry is None:
            fuzzy = self.ontology.fuzzy_medication(ent.raw_value)
            if fuzzy:
                _, entry, score = fuzzy
                method, confidence = "fuzzy", round(score, 4)

        if entry is None:
            return None

        return CodedEntity(
            temp_id=ent.temp_id,
            canonical_code=entry.get("code", ""),
            coding_system="RxNorm",
            normalized_value=entry.get("display", ent.raw_value),
            unit_canonical=None,
            coding_confidence=confidence,
            coding_method=method,
        )

    # ------------------------------------------------------------------ #
    def _code_diagnosis(self, ent: ExtractedEntity) -> Optional[CodedEntity]:
        entry, method, confidence = None, None, None

        if ent.entity_label:
            entry = self.ontology.exact_diagnosis(ent.entity_label)
            if entry:
                method, confidence = "exact", _EXACT_CONFIDENCE

        if entry is None:
            fuzzy = self.ontology.fuzzy_diagnosis(ent.raw_value)
            if fuzzy:
                _, entry, score = fuzzy
                method, confidence = "fuzzy", round(score, 4)

        if entry is None:
            return None

        return CodedEntity(
            temp_id=ent.temp_id,
            canonical_code=entry.get("code", ""),
            coding_system="ICD-10",
            normalized_value=entry.get("display", ent.raw_value),
            unit_canonical=None,
            coding_confidence=confidence,
            coding_method=method,
        )

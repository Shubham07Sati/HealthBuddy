"""
Agent 3: Medical NER & Relations
=================================
Extracts medication, lab-value, and diagnosis mentions from OCR'd text,
classifies each as present/negated/possible/hypothetical, and attaches
a confidence that reflects both OCR quality and extraction certainty.

Architecture note (read this before reaching for spaCy/scispacy/medspacy):
Entity spotting here is dictionary-driven against this project's own
curated ontologies (knowledge_base/ontologies/*.json) rather than a
statistical NER model. See ontology_loader.py's module docstring for
the full reasoning; short version: those files already define exactly
the vocabulary in scope, keyed to the same canonical codes Normalization
needs, and matching against them is deterministic and testable without
downloading/training a model. Swapping in a real biomedical NER model
for better recall on free-text phrasing outside the dictionary is a
legitimate v2 upgrade -- it isn't blocked by anything in this design,
it's just a separate, larger effort (needs a labeled dataset).

What this agent does NOT do (out of scope for this pass, not silently
skipped):
- procedures and body-site entities are not extracted yet.
- vital signs are tagged (the ontology has vital-sign entries mixed
  into the lab dictionary; matches against those keys get
  EntityType.vital_sign instead of EntityType.lab_value).
- entity_date: linking a lab value to the date it was actually drawn
  (as opposed to the document's own timestamp) needs date-string
  parsing near each mention; deferred, so entity_date is always None
  here. Downstream code should not assume it's populated.
- cross-sentence assertion (see assertion.py docstring).
- intra_document_conflicts: left empty here. Detecting "same lab,
  different values in one document" is far more precise once entities
  carry a canonical_code (Normalization's job) instead of a raw dictionary
  key; approximating it on raw text now would produce noisy false
  positives on legitimate multi-timepoint flowsheets. Tracked as a
  follow-up to implement in/after Normalization.
"""
import logging
import time
from typing import List, Tuple
from uuid import uuid4

from app.models.clinical_entity import EntityType
from app.schemas.agent_messages import ClinicalEntitySet, ExtractedEntity, RawExtraction

from . import assertion as assertion_mod
from . import value_parsing as vp
from .ontology_loader import OntologyIndex

log = logging.getLogger(__name__)

# Baseline NER confidence by match "quality". These are heuristic, not
# learned -- an exact long-alias hit with a correctly-parsed value is
# about as sure as a rule-based matcher can be; a short/acronym alias
# with no value attached is the shakiest case we still bother emitting.
_CONF_LONG_ALIAS_WITH_VALUE = 0.93
_CONF_LONG_ALIAS_NO_VALUE = 0.78
_CONF_SHORT_ALIAS_WITH_VALUE = 0.80
_CONF_SHORT_ALIAS_NO_VALUE = 0.55
_CONF_DIAGNOSIS = 0.90
_CONF_MEDICATION_WITH_DOSE = 0.92
_CONF_MEDICATION_NO_DOSE = 0.82


class _SpanOffsetIndex:
    """Maps a character offset in `full_text` back to the OCR TextSpan(s)
    that produced it, so extracted entities inherit real per-region OCR
    confidence instead of the document-wide average. Relies on the OCR
    agent's own construction of full_text as "\\n".join(span.text for
    span in spans) (see ocr/agent.py) -- if that join logic changes,
    this needs to change with it."""

    def __init__(self, raw: RawExtraction):
        self._ranges: List[Tuple[int, int, float]] = []
        pos = 0
        for span in raw.spans:
            start = pos
            end = start + len(span.text)
            self._ranges.append((start, end, span.confidence))
            pos = end + 1  # +1 for the "\n" joiner

    def confidence_for(self, start: int, end: int, fallback: float) -> float:
        overlaps = [
            (min(end, r_end) - max(start, r_start), conf)
            for r_start, r_end, conf in self._ranges
            if r_start < end and r_end > start
        ]
        overlaps = [(w, c) for w, c in overlaps if w > 0]
        if not overlaps:
            return fallback
        total_weight = sum(w for w, _ in overlaps)
        return sum(w * c for w, c in overlaps) / total_weight


class NERAgent:
    """
    Agent 3: Medical NER & Relations
    Extracts entities (medications, labs, diagnoses) from raw text.
    Handles negation and assertion classification.
    """

    def __init__(self):
        self.ontology = OntologyIndex()

    async def extract_entities(self, raw: RawExtraction, patient_id) -> ClinicalEntitySet:
        start_time = time.time()
        log.info(f"Running Medical NER on document {raw.document_id}")

        text = raw.full_text or ""
        if not text.strip():
            log.warning(f"Document {raw.document_id} has no OCR text; skipping NER.")
            return ClinicalEntitySet(
                document_id=raw.document_id,
                patient_id=patient_id,
                entities=[],
                intra_document_conflicts=[],
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

        sentences = assertion_mod.split_sentences(text)
        span_index = _SpanOffsetIndex(raw)

        entities: List[ExtractedEntity] = []
        # Each extractor runs independently -- a failure spotting one
        # entity type (e.g. a malformed ontology entry) shouldn't cost
        # the entities the other extractors already found.
        for extractor, label in (
            (self._extract_labs, "labs"),
            (self._extract_medications, "medications"),
            (self._extract_diagnoses, "diagnoses"),
        ):
            try:
                entities.extend(extractor(text, sentences, span_index, raw.avg_confidence))
            except Exception as exc:
                log.error(f"NER {label} extraction failed for document "
                          f"{raw.document_id}: {exc}", exc_info=True)

        log.info(f"NER extracted {len(entities)} entities from document {raw.document_id}")

        return ClinicalEntitySet(
            document_id=raw.document_id,
            patient_id=patient_id,
            entities=entities,
            intra_document_conflicts=[],
            processing_time_ms=int((time.time() - start_time) * 1000),
        )

    # ------------------------------------------------------------------ #
    # Lab values (+ vitals, same dictionary)
    # ------------------------------------------------------------------ #
    def _extract_labs(self, text, sentences, span_index, doc_avg_conf) -> List[ExtractedEntity]:
        out = []
        for match in self.ontology.find_labs(text):
            parsed = vp.parse_lab_value(text, match.end)
            entity_end = parsed.match_end if parsed else match.end
            is_short = len(match.matched_text) <= 3

            if parsed:
                ner_conf = _CONF_LONG_ALIAS_WITH_VALUE if not is_short else _CONF_SHORT_ALIAS_WITH_VALUE
                raw_value = parsed.value
                unit_raw = parsed.unit or match.unit_canonical
                ambiguity_flag, ambiguity_reason = False, None
            else:
                ner_conf = _CONF_LONG_ALIAS_NO_VALUE if not is_short else _CONF_SHORT_ALIAS_NO_VALUE
                raw_value = match.matched_text
                unit_raw = None
                ambiguity_flag = True
                ambiguity_reason = "Lab name mentioned but no numeric result found nearby."

            is_negated, status, fam_ambig, fam_reason = assertion_mod.classify_assertion(
                sentences, match.start, entity_end
            )
            if fam_ambig:
                ambiguity_flag, ambiguity_reason = fam_ambig, fam_reason

            ocr_conf = span_index.confidence_for(match.start, entity_end, doc_avg_conf)
            out.append(ExtractedEntity(
                temp_id=uuid4().hex,
                entity_type=EntityType.vital_sign if match.is_vital else EntityType.lab_value,
                raw_value=raw_value,
                entity_label=match.canonical_key,
                unit_raw=unit_raw,
                entity_date=None,
                source_span_start=match.start,
                source_span_end=entity_end,
                ocr_confidence=round(ocr_conf, 4),
                ner_confidence=ner_conf,
                combined_confidence=round(ocr_conf * ner_conf, 4),
                is_negated=is_negated,
                assertion_status=status,
                related_entities=[],
                ambiguity_flag=ambiguity_flag,
                ambiguity_reason=ambiguity_reason,
            ))
        return out

    # ------------------------------------------------------------------ #
    # Medications
    # ------------------------------------------------------------------ #
    def _extract_medications(self, text, sentences, span_index, doc_avg_conf) -> List[ExtractedEntity]:
        out = []
        for match in self.ontology.find_medications(text):
            parsed = vp.parse_dosage_and_frequency(text, match.end)
            entity_end = parsed.match_end if parsed else match.end
            is_short = len(match.matched_text) <= 3

            ner_conf = _CONF_MEDICATION_WITH_DOSE if parsed else _CONF_MEDICATION_NO_DOSE
            if is_short:
                ner_conf -= 0.10  # short med aliases (rare in this ontology) are still riskier

            is_negated, status, ambiguity_flag, ambiguity_reason = assertion_mod.classify_assertion(
                sentences, match.start, entity_end
            )

            ocr_conf = span_index.confidence_for(match.start, entity_end, doc_avg_conf)
            out.append(ExtractedEntity(
                temp_id=uuid4().hex,
                entity_type=EntityType.medication,
                raw_value=match.display,
                entity_label=match.canonical_key,
                unit_raw=parsed.combined if parsed else None,
                entity_date=None,
                source_span_start=match.start,
                source_span_end=entity_end,
                ocr_confidence=round(ocr_conf, 4),
                ner_confidence=round(ner_conf, 4),
                combined_confidence=round(ocr_conf * ner_conf, 4),
                is_negated=is_negated,
                assertion_status=status,
                related_entities=[],
                ambiguity_flag=ambiguity_flag,
                ambiguity_reason=ambiguity_reason or None,
            ))
        return out

    # ------------------------------------------------------------------ #
    # Diagnoses
    # ------------------------------------------------------------------ #
    def _extract_diagnoses(self, text, sentences, span_index, doc_avg_conf) -> List[ExtractedEntity]:
        out = []
        for match in self.ontology.find_diagnoses(text):
            is_negated, status, ambiguity_flag, ambiguity_reason = assertion_mod.classify_assertion(
                sentences, match.start, match.end
            )
            ner_conf = _CONF_DIAGNOSIS - (0.10 if len(match.matched_text) <= 3 else 0.0)
            ocr_conf = span_index.confidence_for(match.start, match.end, doc_avg_conf)
            out.append(ExtractedEntity(
                temp_id=uuid4().hex,
                entity_type=EntityType.diagnosis,
                raw_value=match.display,
                entity_label=match.canonical_key,
                unit_raw=None,
                entity_date=None,
                source_span_start=match.start,
                source_span_end=match.end,
                ocr_confidence=round(ocr_conf, 4),
                ner_confidence=round(ner_conf, 4),
                combined_confidence=round(ocr_conf * ner_conf, 4),
                is_negated=is_negated,
                assertion_status=status,
                related_entities=[],
                ambiguity_flag=ambiguity_flag,
                ambiguity_reason=ambiguity_reason or None,
            ))
        return out

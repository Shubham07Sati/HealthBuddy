"""
Ontology lookup for the Normalization agent.

Loads the same three JSON dictionaries NER uses (knowledge_base/ontologies/
loinc_codes.json, rxnorm_icd10_codes.json) so both agents draw on one
source of truth. Two lookup paths:

1. Exact: NER's ExtractedEntity.entity_label carries the dictionary key
   it matched against (e.g. "Hemoglobin", "Metformin"). If present,
   this is a direct O(1) dict lookup -- no re-parsing of raw_value
   needed, and no ambiguity, since it's the same key NER already
   resolved against this same ontology.
2. Fuzzy: for entities without entity_label (e.g. hand-built, or from
   a future non-dictionary NER path), fall back to difflib matching
   against the alias list. Lower confidence, coding_method="fuzzy".
"""
import difflib
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

log = logging.getLogger(__name__)

FUZZY_MATCH_CUTOFF = 0.80


def _find_knowledge_base_dir() -> Path:
    """See app/agents/ner/ontology_loader.py::_find_knowledge_base_dir for
    the full explanation -- same docker-compose mount caveat applies
    here (backend/knowledge_base/ is empty in the container; real data
    lives at the repo root until that mount is fixed)."""
    here = Path(__file__).resolve()
    backend_local = here.parents[3] / "knowledge_base"
    if any(backend_local.rglob("*.json")):
        return backend_local
    for parent in here.parents:
        candidate = parent / "knowledge_base"
        if candidate.is_dir() and any(candidate.rglob("*.json")):
            log.warning("Loaded knowledge_base from %s, not backend/knowledge_base", candidate)
            return candidate
    log.error("Could not locate a populated knowledge_base/ directory.")
    return backend_local


class NormalizationOntology:
    def __init__(self, knowledge_base_dir: Optional[Path] = None):
        self.kb_dir = knowledge_base_dir or _find_knowledge_base_dir()

        self.lab_entries: Dict[str, dict] = {}
        self.med_entries: Dict[str, dict] = {}
        self.diagnosis_entries: Dict[str, dict] = {}

        self._lab_alias_ci: Dict[str, str] = {}
        self._med_alias_ci: Dict[str, str] = {}
        self._diagnosis_alias_ci: Dict[str, str] = {}

        self._load()

    def _load(self) -> None:
        loinc_path = self.kb_dir / "ontologies" / "loinc_codes.json"
        rxnorm_path = self.kb_dir / "ontologies" / "rxnorm_icd10_codes.json"

        try:
            with open(loinc_path) as f:
                loinc = json.load(f).get("loinc_codes", {})
        except Exception as exc:
            log.error(f"Failed to load LOINC ontology from {loinc_path}: {exc}")
            loinc = {}

        try:
            with open(rxnorm_path) as f:
                combined = json.load(f)
                rxnorm = combined.get("rxnorm_codes", {})
                icd10 = combined.get("icd10_codes", {})
        except Exception as exc:
            log.error(f"Failed to load RxNorm/ICD-10 ontology from {rxnorm_path}: {exc}")
            rxnorm, icd10 = {}, {}

        for key, entry in loinc.items():
            self.lab_entries[key] = entry
            for alias in [key] + entry.get("aliases", []):
                self._lab_alias_ci[alias.lower()] = key

        for key, entry in rxnorm.items():
            self.med_entries[key] = entry
            for alias in [key] + entry.get("aliases", []):
                self._med_alias_ci[alias.lower()] = key

        for key, entry in icd10.items():
            self.diagnosis_entries[key] = entry
            for alias in [key] + entry.get("aliases", []):
                self._diagnosis_alias_ci[alias.lower()] = key

    # ------------------------------------------------------------------ #
    # Exact lookup by NER's entity_label
    # ------------------------------------------------------------------ #
    def exact_lab(self, key: str) -> Optional[dict]:
        return self.lab_entries.get(key)

    def exact_medication(self, key: str) -> Optional[dict]:
        return self.med_entries.get(key)

    def exact_diagnosis(self, key: str) -> Optional[dict]:
        return self.diagnosis_entries.get(key)

    # ------------------------------------------------------------------ #
    # Fuzzy fallback by free text (used only when entity_label is absent)
    # ------------------------------------------------------------------ #
    def fuzzy_lab(self, text: str) -> Optional[Tuple[str, dict, float]]:
        return self._fuzzy(text, self._lab_alias_ci, self.lab_entries)

    def fuzzy_medication(self, text: str) -> Optional[Tuple[str, dict, float]]:
        return self._fuzzy(text, self._med_alias_ci, self.med_entries)

    def fuzzy_diagnosis(self, text: str) -> Optional[Tuple[str, dict, float]]:
        return self._fuzzy(text, self._diagnosis_alias_ci, self.diagnosis_entries)

    @staticmethod
    def _fuzzy(text: str, alias_ci: Dict[str, str], entries: Dict[str, dict]
               ) -> Optional[Tuple[str, dict, float]]:
        if not text or not alias_ci:
            return None
        candidates = difflib.get_close_matches(text.lower(), alias_ci.keys(),
                                                n=1, cutoff=FUZZY_MATCH_CUTOFF)
        if not candidates:
            return None
        best_alias = candidates[0]
        score = difflib.SequenceMatcher(None, text.lower(), best_alias).ratio()
        key = alias_ci[best_alias]
        return key, entries[key], score

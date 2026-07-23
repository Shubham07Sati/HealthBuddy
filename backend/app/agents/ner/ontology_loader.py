"""
Ontology-backed alias index for the NER agent.
==============================================
Loads the project's own curated LOINC / RxNorm+ICD-10 dictionaries
(knowledge_base/ontologies/*.json) and turns their alias lists into
compiled regexes for entity spotting.

Why dictionary-driven matching instead of a spaCy/scispacy/medspacy
model pipeline (even though those packages are in requirements.txt):

- This project already ships hand-curated alias lists for exactly the
  entities in scope (labs, vitals, medications, diagnoses), keyed by
  the same canonical codes the Normalization agent expects. A
  dictionary matcher over *this* data is precise, fully deterministic,
  needs no model download, and is testable offline in CI.
- A statistical NER model would out-recall this on free-text phrasing
  it hasn't seen before, but would also need a labeled dataset to
  fine-tune on for this domain, plus model weights shipped/downloaded
  at build time. That's a real v2 upgrade path (see agent.py docstring)
  once there's a training set -- not something to fake in the meantime.

Short aliases (<=3 chars, e.g. "K", "Na", "Cr", "HR") are dangerously
ambiguous against generic prose ("K" could be a stray initial), so
they're matched case-sensitively and only when they appear as a
standalone token. Longer aliases match case-insensitively.
"""
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

SHORT_ALIAS_MAX_LEN = 3


@dataclass(frozen=True)
class AliasMatch:
    start: int
    end: int
    matched_text: str
    canonical_key: str      # dict key in the source JSON, e.g. "Hemoglobin", "Metformin"
    canonical_code: str
    coding_system: str
    display: str
    unit_canonical: Optional[str] = None
    drug_class: Optional[str] = None
    is_vital: bool = False


_VITAL_KEYS = {
    "BloodPressureSystolic", "BloodPressureDiastolic", "HeartRate",
    "Temperature", "OxygenSaturation", "BMI", "Weight", "Height",
}


def _find_knowledge_base_dir() -> Path:
    """
    Resolve the knowledge_base/ directory.

    KNOWN PROJECT ISSUE: docker-compose.yml only bind-mounts ./backend
    into the backend container, but knowledge_base/ lives at the repo
    root (backend/knowledge_base/ is present but empty). So in the
    actual deployed container this directory is empty until either the
    compose file mounts the root-level folder or the data is copied
    into backend/knowledge_base at build time. This loader checks the
    "correct" in-container path first, then falls back to walking up
    parent directories (useful for running tests/scripts from a dev
    checkout) so this agent still works in this repo today, but the
    docker-compose mount should still be fixed.
    """
    here = Path(__file__).resolve()
    backend_local = here.parents[3] / "knowledge_base"  # app/agents/ner/.. -> app -> backend
    if any(backend_local.rglob("*.json")):
        return backend_local

    for parent in here.parents:
        candidate = parent / "knowledge_base"
        if candidate.is_dir() and any(candidate.rglob("*.json")):
            log.warning(
                "Loaded knowledge_base from %s, not backend/knowledge_base -- "
                "see docker-compose mount note in ontology_loader.py",
                candidate,
            )
            return candidate

    log.error("Could not locate a populated knowledge_base/ directory; "
              "NER dictionaries will be empty.")
    return backend_local


class OntologyIndex:
    def __init__(self, knowledge_base_dir: Optional[Path] = None):
        self.kb_dir = knowledge_base_dir or _find_knowledge_base_dir()
        self.lab_entries: Dict[str, dict] = {}
        self.med_entries: Dict[str, dict] = {}
        self.diagnosis_entries: Dict[str, dict] = {}

        self._lab_alias_to_key: Dict[str, str] = {}
        self._med_alias_to_key: Dict[str, str] = {}
        self._diagnosis_alias_to_key: Dict[str, str] = {}

        # Lowercased mirrors, built alongside the case-preserving dicts above,
        # so case-insensitive alias lookup after a regex match is O(1)
        # instead of a linear scan over every alias.
        self._lab_alias_ci: Dict[str, str] = {}
        self._med_alias_ci: Dict[str, str] = {}
        self._diagnosis_alias_ci: Dict[str, str] = {}

        self._load()
        self._lab_pattern_ci, self._lab_pattern_cs = self._build_patterns(self._lab_alias_to_key)
        self._med_pattern_ci, self._med_pattern_cs = self._build_patterns(self._med_alias_to_key)
        self._dx_pattern_ci, self._dx_pattern_cs = self._build_patterns(self._diagnosis_alias_to_key)

    # ------------------------------------------------------------------ #
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
                self._lab_alias_to_key[alias] = key
                self._lab_alias_ci[alias.lower()] = key

        for key, entry in rxnorm.items():
            self.med_entries[key] = entry
            for alias in [key] + entry.get("aliases", []):
                self._med_alias_to_key[alias] = key
                self._med_alias_ci[alias.lower()] = key

        for key, entry in icd10.items():
            self.diagnosis_entries[key] = entry
            for alias in [key] + entry.get("aliases", []):
                self._diagnosis_alias_to_key[alias] = key
                self._diagnosis_alias_ci[alias.lower()] = key

        log.info(
            f"OntologyIndex loaded {len(self._lab_alias_to_key)} lab aliases, "
            f"{len(self._med_alias_to_key)} medication aliases, "
            f"{len(self._diagnosis_alias_to_key)} diagnosis aliases from {self.kb_dir}"
        )

    @staticmethod
    def _build_patterns(alias_to_key: Dict[str, str]):
        """Two compiled alternations: case-insensitive for aliases longer
        than SHORT_ALIAS_MAX_LEN, case-sensitive for short/acronym-like
        ones. Longest-alias-first so e.g. "Insulin Glargine" wins over
        a bare "insulin" substring match, if both existed."""
        long_aliases = sorted(
            (a for a in alias_to_key if len(a) > SHORT_ALIAS_MAX_LEN),
            key=len, reverse=True,
        )
        short_aliases = sorted(
            (a for a in alias_to_key if len(a) <= SHORT_ALIAS_MAX_LEN),
            key=len, reverse=True,
        )

        pattern_ci = None
        if long_aliases:
            escaped = [re.escape(a) for a in long_aliases]
            pattern_ci = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(escaped) + r")(?![A-Za-z0-9])",
                                     re.IGNORECASE)

        pattern_cs = None
        if short_aliases:
            escaped = [re.escape(a) for a in short_aliases]
            pattern_cs = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(escaped) + r")(?![A-Za-z0-9])")

        return pattern_ci, pattern_cs

    # ------------------------------------------------------------------ #
    def _matches(self, text: str, pattern_ci, pattern_cs, alias_to_key, alias_ci, entries,
                 code_field_default_system: str) -> List[AliasMatch]:
        found: List[AliasMatch] = []
        occupied: List[range] = []

        def _try(pattern, case_sensitive: bool):
            if pattern is None:
                return
            for m in pattern.finditer(text):
                span = range(m.start(), m.end())
                if any(span.start < o.stop and span.stop > o.start for o in occupied):
                    continue  # already claimed by a longer/earlier match
                matched_text = m.group(0)
                # Case-sensitive (short/acronym) aliases look themselves up
                # directly; case-insensitive (long) aliases go through the
                # lowercase mirror built at load time.
                canonical_key = alias_to_key.get(matched_text) if case_sensitive \
                    else alias_ci.get(matched_text.lower())
                if canonical_key is None:
                    continue
                entry = entries[canonical_key]
                found.append(AliasMatch(
                    start=m.start(),
                    end=m.end(),
                    matched_text=matched_text,
                    canonical_key=canonical_key,
                    canonical_code=entry.get("code", ""),
                    coding_system=code_field_default_system,
                    display=entry.get("display", canonical_key),
                    unit_canonical=entry.get("unit_canonical"),
                    drug_class=entry.get("drug_class"),
                    is_vital=canonical_key in _VITAL_KEYS,
                ))
                occupied.append(span)

        _try(pattern_ci, case_sensitive=False)
        _try(pattern_cs, case_sensitive=True)
        found.sort(key=lambda a: a.start)
        return found

    def find_labs(self, text: str) -> List[AliasMatch]:
        return self._matches(text, self._lab_pattern_ci, self._lab_pattern_cs,
                              self._lab_alias_to_key, self._lab_alias_ci,
                              self.lab_entries, "LOINC")

    def find_medications(self, text: str) -> List[AliasMatch]:
        return self._matches(text, self._med_pattern_ci, self._med_pattern_cs,
                              self._med_alias_to_key, self._med_alias_ci,
                              self.med_entries, "RxNorm")

    def find_diagnoses(self, text: str) -> List[AliasMatch]:
        return self._matches(text, self._dx_pattern_ci, self._dx_pattern_cs,
                              self._diagnosis_alias_to_key, self._diagnosis_alias_ci,
                              self.diagnosis_entries, "ICD-10")

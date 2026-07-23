"""
Lightweight UCUM-oriented unit normalization for lab values.

This project's ontology (knowledge_base/ontologies/loinc_codes.json)
stores each lab's canonical unit as a human-readable-but-UCUM-adjacent
string (e.g. "g/dL", "10^3/uL", "mIU/L"). What actually comes out of
OCR/NER (`ExtractedEntity.unit_raw`) is whatever the source document
happened to print: different casing, "mcL" vs "uL" vs the literal
micro sign "\u00b5L", "IU/L" vs "IU/l", spelled-out "per", stray
whitespace, etc.

This module does two things, deliberately kept separate because they
carry very different risk:

1. `normalize_unit_string`: syntactic normalization -- map spelling/
   casing/symbol variants of the *same* unit onto one canonical form.
   This is always safe: "MG/DL" and "mg/dl" and "mg/dL" are the same
   unit, just written differently.

2. `units_equivalent`: after syntactic normalization, do the two unit
   strings refer to the same unit? This does NOT attempt cross-system
   unit *conversion* (e.g. mg/dL <-> mmol/L for glucose) -- that needs
   a per-analyte molar-mass conversion factor, and silently applying
   the wrong one for a clinical lab value is a worse failure mode than
   just flagging the mismatch for a human to look at. So when the
   document's unit and the ontology's canonical unit are genuinely
   different systems, this agent surfaces `unit_mismatch=True` and
   lowers coding confidence rather than guessing a conversion.
"""
import re
from typing import Optional

# Canonical UCUM-ish spelling on the right; every left-hand variant
# collapses to it. Keys are already lowercased/whitespace-stripped by
# `normalize_unit_string` before lookup.
_UNIT_ALIAS_MAP = {
    # mass/volume concentration
    "mg/dl": "mg/dL", "mg/100ml": "mg/dL", "mg%": "mg/dL",
    "g/dl": "g/dL", "g/100ml": "g/dL",
    "ng/ml": "ng/mL", "ng/dl": "ng/dL",
    "pg/ml": "pg/mL",
    "ug/dl": "ug/dL", "\u00b5g/dl": "ug/dL", "mcg/dl": "ug/dL",
    # substance concentration
    "mmol/l": "mmol/L", "mmol/lt": "mmol/L",
    "umol/l": "umol/L", "\u00b5mol/l": "umol/L",
    "meq/l": "mEq/L", "meq/lt": "mEq/L",
    "miu/l": "mIU/L", "miu/ml": "mIU/mL",
    "iu/l": "IU/L", "iu/ml": "IU/mL", "u/l": "U/L", "u/ml": "U/mL",
    # counts
    "10^3/ul": "10^3/uL", "10e3/ul": "10^3/uL", "k/ul": "10^3/uL",
    "10^3/l": "10^3/L", "th/ul": "10^3/uL", "thou/ul": "10^3/uL",
    "10^6/ul": "10^6/uL", "m/ul": "10^6/uL",
    "cells/ul": "cells/uL", "/ul": "/uL", "\u00b5l": "uL",
    # ratios / dimensionless
    "%": "%", "percent": "%", "ratio": "ratio",
    # renal / clearance
    "ml/min/1.73m2": "mL/min/1.73m2", "ml/min/1.73 m2": "mL/min/1.73m2",
    "ml/min/1.73m^2": "mL/min/1.73m2",
    # vitals / anthropometrics
    "mmhg": "mmHg", "bpm": "bpm", "kg/m2": "kg/m2", "kg/m^2": "kg/m2",
    "c": "\u00b0C", "\u00b0c": "\u00b0C", "degc": "\u00b0C",
    "kg": "kg", "cm": "cm",
}

# Units that are genuinely different measurement systems for the same
# quantity -- pairs where a mismatch is a *real* discrepancy worth
# flagging (as opposed to just an unfamiliar spelling this map hasn't
# seen yet, which normalize_unit_string already handles).
_KNOWN_CROSS_SYSTEM_PAIRS = {
    frozenset({"mg/dL", "mmol/L"}),
    frozenset({"g/dL", "mmol/L"}),
    frozenset({"ug/dL", "nmol/L"}),
    frozenset({"ng/mL", "pmol/L"}),
    frozenset({"IU/L", "ukat/L"}),
}

_WS_RE = re.compile(r"\s+")


def normalize_unit_string(raw: Optional[str]) -> Optional[str]:
    """Collapse whitespace/casing/symbol variants to a canonical
    spelling. Returns None unchanged if input is None/empty; returns
    the original (whitespace-collapsed) string if no alias is known,
    since an unrecognized-but-verbatim unit is still more useful
    downstream than discarding it."""
    if not raw:
        return None
    cleaned = _WS_RE.sub(" ", raw.strip())
    if not cleaned:
        return None
    key = cleaned.lower().replace(" ", "")
    return _UNIT_ALIAS_MAP.get(key, cleaned)


def units_equivalent(unit_a: Optional[str], unit_b: Optional[str]) -> bool:
    """True if two (already-normalized-or-raw) unit strings denote the
    same unit after syntactic normalization. Missing units on either
    side are treated as "not comparable" -> True (nothing to conflict
    with), consistent with this agent's conservative stance on
    flagging only genuine, evidenced mismatches."""
    if not unit_a or not unit_b:
        return True
    na, nb = normalize_unit_string(unit_a), normalize_unit_string(unit_b)
    return na is None or nb is None or na.lower() == nb.lower()


def is_cross_system_mismatch(unit_a: Optional[str], unit_b: Optional[str]) -> bool:
    """True only for unit pairs known to represent the same *quantity*
    but a different measurement system (e.g. mass/volume vs molar
    concentration) -- the case worth a confidence penalty and an
    explicit flag, as opposed to a unit this map simply doesn't
    recognize yet."""
    if not unit_a or not unit_b:
        return False
    na, nb = normalize_unit_string(unit_a), normalize_unit_string(unit_b)
    if na is None or nb is None or na == nb:
        return False
    return frozenset({na, nb}) in _KNOWN_CROSS_SYSTEM_PAIRS

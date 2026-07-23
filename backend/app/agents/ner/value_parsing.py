"""
Structured value parsing for lab results and medication dosing.

Entity spotting (ontology_loader) tells us *where* a lab name or drug
name is; this module answers "and what value/dosage goes with it",
by looking in a small window of text immediately after the mention.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

NUMBER_RE = r"[-+]?\d+(?:\.\d+)?"

# Ordered longest-first so "mL/min/1.73m2" matches before a bare "m2" would.
KNOWN_UNITS = [
    "mL/min/1.73m2", "mL/min/1.73 m2", "10^3/uL", "mmol/L", "mIU/L", "mEq/L",
    "mg/dL", "g/dL", "U/L", "kg/m2", "bpm", "mmHg", "ratio", "IU", "kg", "cm",
    "%", "°C",
]
_UNIT_ALTERNATION = "|".join(re.escape(u) for u in sorted(KNOWN_UNITS, key=len, reverse=True))

# e.g. "Hemoglobin: 12.1 g/dL", "Hemoglobin - 12.1g/dL", "Hemoglobin 12.1"
LAB_VALUE_RE = re.compile(
    rf"^\s*[:\-=]?\s*({NUMBER_RE})\s*({_UNIT_ALTERNATION})?", re.IGNORECASE
)

DOSAGE_RE = re.compile(
    rf"^\s*[:\-]?\s*({NUMBER_RE})\s*(mg|mcg|g|units?|IU|mL)\b", re.IGNORECASE
)

FREQUENCY_PATTERNS = [
    (re.compile(r"\bonce\s+daily\b|\bOD\b|\bQD\b", re.IGNORECASE), "once daily"),
    (re.compile(r"\btwice\s+daily\b|\bBD\b|\bBID\b", re.IGNORECASE), "twice daily"),
    (re.compile(r"\bthree\s+times\s+daily\b|\bTDS\b|\bTID\b", re.IGNORECASE), "three times daily"),
    (re.compile(r"\bfour\s+times\s+daily\b|\bQID\b", re.IGNORECASE), "four times daily"),
    (re.compile(r"\bat\s+night\b|\bnightly\b|\bQHS\b", re.IGNORECASE), "at night"),
    (re.compile(r"\bas\s+needed\b|\bPRN\b", re.IGNORECASE), "as needed"),
    (re.compile(r"\bweekly\b", re.IGNORECASE), "weekly"),
]

# How far past an entity mention to look for its value/dosage/frequency.
# Generous enough for "Hemoglobin ................. 12.1 g/dL" style
# lab-report layouts (dot leaders / whitespace from table-to-text
# flattening) without spilling into the next line's unrelated content.
LOOKAHEAD_CHARS = 60


@dataclass
class ParsedLabValue:
    value: str
    unit: Optional[str]
    match_end: int  # absolute offset in the source text


@dataclass
class ParsedDosage:
    combined: str  # e.g. "1000mg BD" -- matches the shape normalization/agent.py already expects
    match_end: int


def parse_lab_value(text: str, after_idx: int) -> Optional[ParsedLabValue]:
    window = text[after_idx: after_idx + LOOKAHEAD_CHARS]
    # Don't let the window run past a newline/period -- that's a new
    # field or sentence, not this lab's result.
    cutoff = min([i for i in (window.find("\n"), len(window)) if i != -1], default=len(window))
    window = window[:cutoff]

    m = LAB_VALUE_RE.match(window)
    if not m:
        return None
    return ParsedLabValue(
        value=m.group(1),
        unit=m.group(2),
        match_end=after_idx + m.end(),
    )


FREQUENCY_LOOKAHEAD_CHARS = 20  # tight on purpose -- see note below


def parse_dosage_and_frequency(text: str, after_idx: int) -> Optional[ParsedDosage]:
    window = text[after_idx: after_idx + LOOKAHEAD_CHARS]
    cutoff = min([i for i in (window.find("\n"), len(window)) if i != -1], default=len(window))
    window = window[:cutoff]

    dose_m = DOSAGE_RE.match(window)

    # Frequency is searched in a short window starting right after the
    # dosage (or right after the drug mention if no dosage matched),
    # NOT across the full LOOKAHEAD_CHARS window used for dosage: a
    # 60-char lookahead is wide enough to reach into the *next* drug's
    # dosage/frequency on a densely packed medication list line (e.g.
    # "Metformin 1000mg BD. Lisinopril 10mg OD."), which would
    # misattribute "OD" to Metformin. A tight post-dosage window avoids
    # that without needing full sentence boundary detection.
    freq_search_start = dose_m.end() if dose_m else 0
    freq_window = window[freq_search_start: freq_search_start + FREQUENCY_LOOKAHEAD_CHARS]
    freq_text = None
    for pattern, label in FREQUENCY_PATTERNS:
        if pattern.search(freq_window):
            freq_text = label
            break

    if not dose_m and not freq_text:
        return None

    parts: List[str] = []
    match_end = after_idx
    if dose_m:
        parts.append(f"{dose_m.group(1)}{dose_m.group(2)}")
        match_end = after_idx + dose_m.end()
    if freq_text:
        parts.append(freq_text)

    return ParsedDosage(combined=" ".join(parts), match_end=match_end)

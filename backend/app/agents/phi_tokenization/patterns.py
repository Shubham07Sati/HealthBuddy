"""
PHI Detection Patterns
=======================
Rule-based (regex + deterministic logic) detection patterns for
Protected Health Information. Deliberately NOT an LLM/ML approach --
these patterns need to be fast, deterministic, auditable, and safe to
run synchronously in the pipeline on every document.

Each entry in `PHI_PATTERNS` is a `PHIPatternSpec` with:
    - `category`:   canonical PHI category name (used in token prefix
                    and in the stored mapping's metadata)
    - `pattern`:    compiled regex
    - `token_prefix`: the literal prefix used when building tokens,
                      e.g. "PATIENT", "DOB", "PHONE", "MRN"
    - `priority`:   lower number = matched/resolved first when spans
                    overlap (e.g. MRN should win over a generic
                    numeric-ID pattern)

Ordering matters: `PHITokenizer` resolves overlapping matches by
priority (and, as a tiebreaker, longest match wins), so more specific
patterns (MRN, Aadhaar, PAN) are listed with a lower priority number
than generic catch-alls.

NOTE: This module intentionally does not import anything from
`app.core.security` -- that module already contains a narrower
LLM-guardrail PHI tokenizer (`PHITokenizer` there, scoped to
"redact before calling an external LLM"). This module is the
pipeline-stage PHI tokenizer (OCR -> PHI Tokenization -> NER) and has
a broader, healthcare-record-specific pattern set (Aadhaar, PAN,
ages, hospital/patient IDs, etc.) required by the ingestion pipeline.
The two are complementary, not duplicative: this module could
reuse `app.core.security.encrypt_phi` for at-rest encryption of the
token map (see `storage.py`), which is exactly the extension point
requested for future Fernet integration.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PHIPatternSpec:
    category: str
    token_prefix: str
    pattern: re.Pattern[str]
    priority: int


# ---------------------------------------------------------------------- #
# Individual patterns
# ---------------------------------------------------------------------- #

# Medical Record Number -- "MRN: 123456", "MRN-00123456", "MRN 12345"
_MRN = re.compile(r"\bMRN[:\s#-]*\d{5,12}\b", re.IGNORECASE)

# Hospital ID -- "Hospital ID: H-2024-00123", "Hosp ID# HOSP12345"
_HOSPITAL_ID = re.compile(
    r"\b(?:Hospital\s?ID|Hosp\.?\s?ID|HID)[:\s#-]*[A-Z0-9-]{4,20}\b",
    re.IGNORECASE,
)

# Patient ID -- "Patient ID: P-000123", "PID# 4432"
_PATIENT_ID = re.compile(
    r"\b(?:Patient\s?ID|PID)[:\s#-]*[A-Z0-9-]{3,20}\b",
    re.IGNORECASE,
)

# Aadhaar (India) -- 12 digits, optionally grouped 4-4-4, optionally
# preceded by a label. Matched before generic phone numbers since
# Aadhaar is 12 digits vs. 10 for Indian mobile numbers.
_AADHAAR = re.compile(
    r"\b(?:Aadhaar|Aadhar|UID)[:\s#-]*\d{4}\s?\d{4}\s?\d{4}\b|\b\d{4}\s\d{4}\s\d{4}\b",
    re.IGNORECASE,
)

# PAN (India) -- 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F)
_PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")

# Date of birth -- "DOB: 12/05/1980", "Date of Birth: 1980-05-12"
_DOB = re.compile(
    r"\b(?:DOB|D\.O\.B\.?|Date of Birth)[:\s]*"
    r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
    re.IGNORECASE,
)

# Age -- "Age: 45", "45 years old", "45 y/o", "45yo", "age 45 yrs"
_AGE = re.compile(
    r"\b(?:Age[:\s]*\d{1,3}(?:\s?(?:years?|yrs?)(?:\sold)?)?"
    r"|\d{1,3}\s?(?:years?[\s-]old|yrs?[\s-]old|y/?o))\b",
    re.IGNORECASE,
)

# Phone numbers -- US-style (with or without parens around the area
# code) and generic 10-digit Indian mobile numbers. The parenthesized
# form is matched as its own alternative (rather than an optional
# `\(?...\)?` inside a single `\b`-anchored pattern) so the leading
# "(" is actually included in the match instead of left dangling.
_PHONE = re.compile(
    r"\(\d{3}\)[-.\s]?\d{3}[-.\s]\d{4}\b"
    r"|\+?\b(?:1[-.\s]?)?\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"
    r"|\+?\b(?:91[-.\s]?)?[6-9]\d{9}\b"
)

# Email addresses
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Patient / provider names -- title-cased name preceded by an
# honorific or explicit "Patient" label. Deliberately conservative
# (requires a preceding cue word) to keep false-positive rate low on
# clinical prose that is otherwise full of capitalized medical terms.
_NAME = re.compile(
    r"\b(?:Patient(?:\sName)?|Pt\.?|Dr\.?|Doctor|Mr\.?|Mrs\.?|Ms\.?|Prof\.?|Sri|Smt\.?)"
    r"[:\s]+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b"
)

# Street addresses -- "123 Main St", "45 MG Road"
_ADDRESS = re.compile(
    r"\b\d{1,5}\s+[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){0,4}\s+"
    r"(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Lane|Ln|Way|Court|Ct|Nagar|Marg|Colony)\b",
    re.IGNORECASE,
)

# National Provider Identifier (US) -- kept for parity with existing
# app.core.security patterns; not strictly PHI of the *patient* but a
# common adjacent identifier worth tokenizing consistently.
_NPI = re.compile(r"\bNPI[:\s]*\d{10}\b", re.IGNORECASE)


# ---------------------------------------------------------------------- #
# Registry -- ORDER IS SIGNIFICANT (used as a priority tiebreak in
# addition to the explicit `priority` field).
# ---------------------------------------------------------------------- #
PHI_PATTERNS: list[PHIPatternSpec] = [
    PHIPatternSpec("MRN", "MRN", _MRN, priority=0),
    PHIPatternSpec("HOSPITAL_ID", "HOSPID", _HOSPITAL_ID, priority=1),
    PHIPatternSpec("PATIENT_ID", "PID", _PATIENT_ID, priority=1),
    PHIPatternSpec("AADHAAR", "AADHAAR", _AADHAAR, priority=1),
    PHIPatternSpec("PAN", "PAN", _PAN, priority=1),
    PHIPatternSpec("DOB", "DOB", _DOB, priority=2),
    PHIPatternSpec("AGE", "AGE", _AGE, priority=3),
    PHIPatternSpec("EMAIL", "EMAIL", _EMAIL, priority=3),
    PHIPatternSpec("PHONE", "PHONE", _PHONE, priority=4),
    PHIPatternSpec("NPI", "NPI", _NPI, priority=4),
    PHIPatternSpec("NAME", "PATIENT", _NAME, priority=5),
    PHIPatternSpec("ADDRESS", "ADDR", _ADDRESS, priority=6),
]

# Recognizes any token this module could have produced, for detokenization.
TOKEN_PATTERN = re.compile(
    r"\[\[PHI:(?P<prefix>[A-Z]+):(?P<uuid>[0-9a-fA-F-]{36})\]\]"
)

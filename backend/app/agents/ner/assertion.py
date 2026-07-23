"""
Assertion classification: is this entity actually present, negated,
hypothetical, uncertain, or someone else's (family history)?

This is a small, explicit rule set in the spirit of the ConText
algorithm (Chapman et al.) rather than a full medspacy ConText
pipeline: a fixed list of trigger phrases scoped to the entity's own
sentence, checked before and after the mention. It is deliberately
conservative -- ambiguous cases fall through to "present" plus an
ambiguity flag rather than guessing, since silently mislabeling a
present finding as negated (or vice versa) is a worse failure mode for
a clinical system than surfacing it for review.

Known limitation, left as a v2 item: this cannot resolve triggers that
apply across sentence boundaries (e.g. "No significant findings.
Hemoglobin remains low." -- the negation in sentence 1 doesn't apply to
sentence 2, which is correct here, but a case like "Denies:\n- chest
pain\n- Metformin use" spanning a colon+list would be missed). A real
ConText/medspacy pass over parsed sentences would handle list-style
structures; this rule set only looks within one sentence.
"""
import re
from dataclasses import dataclass
from typing import List, Tuple

from app.models.clinical_entity import AssertionStatus

# Ordered by specificity -- checked in this order per side.
_PRE_NEGATION = [
    r"\bno evidence of\b", r"\bno signs of\b", r"\bnegative for\b",
    r"\bdenies\b", r"\bdenied\b", r"\bwithout\b", r"\babsence of\b",
    r"\bnot on\b", r"\bdiscontinued\b", r"\bruled out\b", r"\bfree of\b",
    r"\bno\b",
]
_POST_NEGATION = [
    r"\bwas ruled out\b", r"\bwas negative\b", r"\bnot detected\b",
    r"\bhas resolved\b", r"\bwas discontinued\b",
]
_HYPOTHETICAL = [
    r"\bif\b", r"\bshould\b", r"\bin the event of\b", r"\bin case of\b",
    r"\bwould require\b", r"\bmay require\b",
]
_POSSIBLE = [
    r"\bpossible\b", r"\bprobable\b", r"\blikely\b", r"\bsuspected\b",
    r"\bquestionable\b", r"\bconcern for\b", r"\bconsider(?:ing)?\b", r"\?",
]
_CONDITIONAL = [
    r"\bas needed\b", r"\bPRN\b", r"\bif needed\b", r"\bif required\b",
]
_FAMILY_HISTORY = [
    r"\bfamily history of\b", r"\bmother has\b", r"\bfather has\b",
    r"\bsibling with\b", r"\bmaternal\b", r"\bpaternal\b",
]

_PRE_WINDOW_CHARS = 45   # how far before the entity, within the sentence, to look
_POST_WINDOW_CHARS = 25  # how far after


def _compile(patterns: List[str]) -> re.Pattern:
    return re.compile("|".join(patterns), re.IGNORECASE)


_PRE_NEG_RE = _compile(_PRE_NEGATION)
_POST_NEG_RE = _compile(_POST_NEGATION)
_HYPOTHETICAL_RE = _compile(_HYPOTHETICAL)
_POSSIBLE_RE = _compile(_POSSIBLE)
_CONDITIONAL_RE = _compile(_CONDITIONAL)
_FAMILY_RE = _compile(_FAMILY_HISTORY)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass
class SentenceSpan:
    text: str
    start: int  # offset in the original full_text
    end: int


def split_sentences(full_text: str) -> List[SentenceSpan]:
    """Offset-preserving sentence split. Not linguistically perfect
    (doesn't special-case 'Dr.' or decimal numbers like '1.5 mg'), but
    good enough to scope assertion-trigger search to "this clinical
    statement" rather than the whole document, which is what matters
    here -- an occasional over/under-split just widens or narrows the
    trigger-search window slightly."""
    spans: List[SentenceSpan] = []
    pos = 0
    for m in _SENTENCE_SPLIT_RE.finditer(full_text):
        spans.append(SentenceSpan(text=full_text[pos:m.start()], start=pos, end=m.start()))
        pos = m.end()
    spans.append(SentenceSpan(text=full_text[pos:], start=pos, end=len(full_text)))
    return [s for s in spans if s.text.strip()]


def find_sentence(sentences: List[SentenceSpan], char_offset: int) -> SentenceSpan:
    for s in sentences:
        if s.start <= char_offset < s.end:
            return s
    # Fall back to the last sentence if offset lands exactly at EOF etc.
    return sentences[-1] if sentences else SentenceSpan("", 0, 0)


def classify_assertion(
    sentences: List[SentenceSpan], entity_start: int, entity_end: int
) -> Tuple[bool, AssertionStatus, bool, str]:
    """
    Returns (is_negated, assertion_status, ambiguity_flag, ambiguity_reason).
    """
    sentence = find_sentence(sentences, entity_start)
    rel_start = entity_start - sentence.start
    rel_end = entity_end - sentence.start

    pre_window = sentence.text[max(0, rel_start - _PRE_WINDOW_CHARS):rel_start]
    post_window = sentence.text[rel_end: rel_end + _POST_WINDOW_CHARS]

    if _FAMILY_RE.search(pre_window):
        return (
            False, AssertionStatus.conditional, True,
            "Mentioned in a family-history context, not necessarily the patient's own finding.",
        )

    if _PRE_NEG_RE.search(pre_window) or _POST_NEG_RE.search(post_window):
        return False, AssertionStatus.absent, False, ""

    if _HYPOTHETICAL_RE.search(pre_window):
        return False, AssertionStatus.hypothetical, False, ""

    if _CONDITIONAL_RE.search(pre_window) or _CONDITIONAL_RE.search(post_window):
        return False, AssertionStatus.conditional, False, ""

    if _POSSIBLE_RE.search(pre_window) or _POSSIBLE_RE.search(post_window):
        return False, AssertionStatus.possible, False, ""

    return False, AssertionStatus.present, False, ""

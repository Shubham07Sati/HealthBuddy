"""
PHI Tokenizer
=============
Stateless detection + deterministic tokenization/detokenization logic.
No I/O happens here -- persistence is delegated to a `TokenMappingStore`
(see storage.py) by the caller (`agent.py`). This keeps the detection
rules independently unit-testable.

Determinism: the same (category, original_value) pair always produces
the same token, via `uuid.uuid5` against a fixed namespace. This means
repeated occurrences of the same PHI value within a document (e.g. a
patient's name mentioned five times) collapse to a single token, and
re-tokenizing identical input is idempotent/reproducible -- which is
what "deterministic tokens" means in the requirements, as opposed to
a fresh random UUID per occurrence.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .patterns import PHI_PATTERNS, TOKEN_PATTERN, PHIPatternSpec

log = logging.getLogger(__name__)

# Fixed namespace so tokens are reproducible across processes/restarts
# given the same (category, value) input.
_TOKEN_NAMESPACE = uuid.UUID("6f6f9c2e-6b0a-4e3a-9f1a-9d1b8f9c9a11")


@dataclass(frozen=True)
class PHIMatch:
    start: int
    end: int
    category: str
    token_prefix: str
    priority: int
    value: str


class PHITokenizer:
    """Rule-based PHI detector/tokenizer/detokenizer.

    This class holds no mutable state and is safe to share across
    concurrent async tasks/requests.
    """

    def __init__(self, patterns: List[PHIPatternSpec] | None = None) -> None:
        self._patterns = patterns if patterns is not None else PHI_PATTERNS

    # ------------------------------------------------------------------ #
    # Detection
    # ------------------------------------------------------------------ #
    def detect(self, text: str) -> List[PHIMatch]:
        """Find all PHI spans in `text`, resolving overlaps.

        Overlap resolution: lower `priority` wins; ties broken by
        longer match; further ties broken by earliest start offset.
        This keeps e.g. "MRN: 123456789012" from also being partially
        re-matched as an Aadhaar number.
        """
        candidates: List[PHIMatch] = []
        for spec in self._patterns:
            try:
                for m in spec.pattern.finditer(text):
                    candidates.append(PHIMatch(
                        start=m.start(),
                        end=m.end(),
                        category=spec.category,
                        token_prefix=spec.token_prefix,
                        priority=spec.priority,
                        value=m.group(0),
                    ))
            except Exception as exc:
                # A malformed/pathological pattern shouldn't take down
                # detection for every other category.
                log.error(f"PHI pattern for category '{spec.category}' raised "
                          f"during matching: {exc}", exc_info=True)

        candidates.sort(key=lambda c: (c.priority, -(c.end - c.start), c.start))

        accepted: List[PHIMatch] = []
        occupied: List[Tuple[int, int]] = []
        for cand in candidates:
            if any(cand.start < e and cand.end > s for s, e in occupied):
                continue  # overlaps a higher-priority/longer match already accepted
            accepted.append(cand)
            occupied.append((cand.start, cand.end))

        accepted.sort(key=lambda c: c.start)
        return accepted

    # ------------------------------------------------------------------ #
    # Tokenization
    # ------------------------------------------------------------------ #
    @staticmethod
    def make_token(category: str, token_prefix: str, value: str) -> str:
        """Build a deterministic token for a (category, value) pair.

        Format: ``[[PHI:<PREFIX>:<uuid5>]]`` -- bracketed and namespaced
        so it survives OCR-adjacent text munging and is trivially
        distinguishable from clinical content by `TOKEN_PATTERN`.
        """
        token_uuid = uuid.uuid5(_TOKEN_NAMESPACE, f"{category}:{value}")
        return f"[[PHI:{token_prefix}:{token_uuid}]]"

    def tokenize(self, text: str) -> Tuple[str, Dict[str, Dict[str, str]]]:
        """Replace all detected PHI spans with deterministic tokens.

        Returns
        -------
        (tokenized_text, mapping)
            `mapping` is ``{token: {"value": original_value, "category": category}}``,
            ready to hand to a `TokenMappingStore.save_mapping`.
        """
        if not text:
            return text, {}

        matches = self.detect(text)
        if not matches:
            return text, {}

        mapping: Dict[str, Dict[str, str]] = {}
        pieces: List[str] = []
        cursor = 0
        for m in matches:
            pieces.append(text[cursor:m.start])
            token = self.make_token(m.category, m.token_prefix, m.value)
            mapping[token] = {"value": m.value, "category": m.category}
            pieces.append(token)
            cursor = m.end
        pieces.append(text[cursor:])

        tokenized = "".join(pieces)
        log.debug(
            f"PHI tokenization replaced {len(matches)} span(s) across "
            f"{len({m.category for m in matches})} categor(y/ies)"
        )
        return tokenized, mapping

    # ------------------------------------------------------------------ #
    # Detokenization
    # ------------------------------------------------------------------ #
    def detokenize(self, text: str, mapping: Dict[str, Dict[str, str]]) -> str:
        """Restore original values for every recognizable token in `text`
        using the provided `mapping` (``{token: {"value": ..., "category": ...}}``).

        Tokens present in `text` but absent from `mapping` are left
        in place and logged, rather than raising -- a missing mapping
        entry (e.g. store eviction) shouldn't crash a downstream
        display/report step.
        """
        if not text:
            return text

        def _replace(match) -> str:
            token = match.group(0)
            record = mapping.get(token)
            if record is None:
                log.warning(f"PHI token not found in mapping during detokenize: {token}")
                return token
            return record["value"]

        return TOKEN_PATTERN.sub(_replace, text)

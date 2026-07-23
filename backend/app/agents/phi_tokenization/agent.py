"""
Agent 2.5: PHI Tokenization
===========================
Runs between OCR and Medical NER (see agents/orchestrator/pipeline.py's
`node_phi_tokenization`). Detects PHI in the OCR'd text using
rule-based, deterministic detection (`tokenizer.PHITokenizer`) and
replaces it with opaque tokens before any downstream agent -- NER,
Normalization, Trend, Knowledge, Reasoning, Verification, and any LLM
call inside those -- ever sees the raw text.

Design notes
------------
- Operates on `RawExtraction` (the OCR agent's output schema) and
  returns a `RawExtraction` with the same shape, so no other agent's
  interface has to change: NER already consumes `RawExtraction` and
  rebuilds its own span-offset index from `full_text = "\\n".join(...)`
  (see ner/agent.py's `_SpanOffsetIndex`), so this agent tokenizes each
  `TextSpan.text` individually and rebuilds `full_text` with the exact
  same join logic the OCR agent uses, keeping character offsets valid
  for every downstream consumer.
- The reversible mapping is written once per document via a
  `TokenMappingStore` (default: in-memory; swappable for Redis/DB --
  see storage.py) so a later stage (e.g. Verification, or a
  clinician-facing report) can detokenize on demand.
- Detection/replacement never raises for a single bad pattern (see
  `PHITokenizer.detect`); this agent's own try/except boundary exists
  so a hard failure (e.g. store unavailable) surfaces as a clean,
  logged exception that the orchestrator's `guarded_node` wrapper can
  route to `error_handler`, exactly like every other agent.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Optional
from uuid import UUID

from app.core.config import get_settings
from app.schemas.agent_messages import RawExtraction, TextSpan

from .storage import InMemoryTokenMappingStore, TokenMappingStore
from .tokenizer import PHITokenizer

log = logging.getLogger(__name__)
settings = get_settings()


class PHITokenizationAgent:
    """Agent 2.5: PHI Tokenization.

    Detects and tokenizes PHI in OCR output before it reaches NER or
    any other downstream/LLM-backed agent.
    """

    def __init__(
        self,
        store: Optional[TokenMappingStore] = None,
        tokenizer: Optional[PHITokenizer] = None,
    ) -> None:
        self._store: TokenMappingStore = store or InMemoryTokenMappingStore()
        self._tokenizer = tokenizer or PHITokenizer()

    # ------------------------------------------------------------------ #
    # Public entry point, called by the orchestrator                     #
    # ------------------------------------------------------------------ #
    async def tokenize(self, raw: RawExtraction) -> RawExtraction:
        """Return a copy of `raw` with all detected PHI spans replaced by
        deterministic tokens, and persist the reversible mapping.

        If PHI tokenization is disabled via configuration
        (`settings.phi_redaction_enabled`), `raw` is returned unchanged
        -- this mirrors the existing opt-out flag already used by
        `app.core.security.PHITokenizer.tokenize_for_llm`.
        """
        start = time.time()

        if not settings.phi_redaction_enabled:
            log.info(
                f"PHI tokenization disabled via settings; passing document "
                f"{raw.document_id} through unmodified"
            )
            return raw

        try:
            new_spans: list[TextSpan] = []
            merged_mapping: Dict[str, Dict[str, str]] = {}

            for span in raw.spans:
                tokenized_text, span_mapping = self._tokenizer.tokenize(span.text)
                if span_mapping:
                    merged_mapping.update(span_mapping)
                new_spans.append(
                    span.model_copy(update={"text": tokenized_text})
                    if tokenized_text != span.text
                    else span
                )

            # Rebuild full_text with the SAME join logic the OCR agent
            # uses (see ocr/agent.py), so NER's _SpanOffsetIndex offsets
            # continue to line up against the tokenized text.
            full_text = "\n".join(s.text for s in new_spans)

            # low_confidence_spans is a filtered view of `spans` by the
            # same threshold the OCR agent used -- recompute it against
            # the (now tokenized) spans rather than trying to patch the
            # old list, since span identity changed.
            low_confidence = [
                s for s in new_spans if s.confidence < settings.ocr_confidence_threshold
            ]

            if merged_mapping:
                await self._store.save_mapping(str(raw.document_id), merged_mapping)
                categories = sorted({v["category"] for v in merged_mapping.values()})
                log.info(
                    f"PHI tokenization for document {raw.document_id}: "
                    f"{len(merged_mapping)} token(s) across categories {categories} "
                    f"in {int((time.time() - start) * 1000)}ms"
                )
            else:
                log.info(
                    f"PHI tokenization for document {raw.document_id}: no PHI "
                    f"detected in {int((time.time() - start) * 1000)}ms"
                )

            return raw.model_copy(update={
                "spans": new_spans,
                "full_text": full_text,
                "low_confidence_spans": low_confidence,
            })

        except Exception as exc:
            log.error(
                f"PHI tokenization failed for document {raw.document_id}: {exc}",
                exc_info=True,
            )
            raise

    # ------------------------------------------------------------------ #
    # Detokenization (for later use by reporting / audit / clinician UI)  #
    # ------------------------------------------------------------------ #
    async def detokenize_text(self, document_id: UUID | str, text: str) -> str:
        """Restore original PHI values in `text` using the stored mapping
        for `document_id`. Safe to call even if no PHI was ever detected
        for that document (returns `text` unchanged)."""
        try:
            mapping = await self._store.get_mapping(str(document_id))
            if not mapping:
                return text
            return self._tokenizer.detokenize(text, mapping)
        except Exception as exc:
            log.error(
                f"PHI detokenization failed for document {document_id}: {exc}",
                exc_info=True,
            )
            raise

    async def get_mapping(self, document_id: UUID | str) -> Dict[str, Dict[str, str]]:
        """Return the full stored token map for a document."""
        return await self._store.get_mapping(str(document_id))

    async def purge_mapping(self, document_id: UUID | str) -> None:
        """Delete all stored tokens for a document (e.g. retention/GDPR-style purge)."""
        await self._store.delete_mapping(str(document_id))

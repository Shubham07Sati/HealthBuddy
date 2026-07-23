"""
Agent 2.5: PHI Tokenization
===========================
Runs immediately after OCR and before Medical NER. Detects Protected
Health Information (PHI) in raw OCR text using deterministic,
rule-based (regex) detection -- no LLM involved -- and replaces each
detected span with an opaque, deterministic token
(e.g. ``PATIENT_<uuid>``, ``DOB_<uuid>``, ``PHONE_<uuid>``,
``MRN_<uuid>``).

The reversible token -> original-value mapping is persisted behind a
storage interface (`storage.TokenMappingStore`) so the backing store
can be swapped from in-memory to Redis or Postgres later without
touching the detection/tokenization logic. See `storage.py` for the
interface and the in-memory reference implementation used by default.

Public surface:
    - `agent.PHITokenizationAgent`   the orchestrator-facing agent
    - `tokenizer.PHITokenizer`       stateless detect/tokenize/detokenize
    - `patterns.PHI_PATTERNS`        the regex detection rules
    - `storage.TokenMappingStore`    storage interface
    - `storage.InMemoryTokenMappingStore` default backend
"""
from .agent import PHITokenizationAgent

__all__ = ["PHITokenizationAgent"]

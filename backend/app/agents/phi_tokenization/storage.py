"""
Token Mapping Storage
======================
Isolates the reversible token -> original-value mapping behind an
abstract interface (`TokenMappingStore`) so the backing store can be
swapped later (Redis, Postgres) without changing `tokenizer.py` or
`agent.py`.

Concurrency: `InMemoryTokenMappingStore` is the default, dev/single-
process backend. It is safe for concurrent async requests within one
process via an `asyncio.Lock` per document, but -- like the
LangGraph `MemorySaver` checkpointer already used by the orchestrator
(see agents/orchestrator/pipeline.py) -- it does NOT survive across
separate Celery worker processes or restarts. A Redis-backed store is
the natural next step (mirrors `services/cache.py` and the existing
`app.core.security.PHITokenizer`, which already persists PHI token
mappings in Redis) and can be dropped in by implementing
`TokenMappingStore` and swapping the instance the agent is
constructed with; no other file needs to change.

Encryption hook: `set_encryption` lets a store encrypt values at rest
using the project's existing Fernet helpers
(`app.core.security.encrypt_phi` / `decrypt_phi`) without changing the
public `get`/`set` contract -- this is the extension point for wiring
in Fernet encryption and, later, an Audit Ledger write on every
mapping mutation.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional

log = logging.getLogger(__name__)

# A single token's stored record: the original plaintext value plus
# the PHI category it was detected as (useful for audit/debugging
# without needing to re-run detection).
TokenRecord = Dict[str, str]  # {"value": ..., "category": ...}


class TokenMappingStoreError(Exception):
    """Raised when the token mapping store cannot complete an operation."""


class TokenMappingStore(ABC):
    """Abstract reversible token <-> original-value mapping store.

    Implementations MUST be safe for concurrent use across multiple
    simultaneous document-processing requests.
    """

    @abstractmethod
    async def save_mapping(
        self, document_id: str, mapping: Dict[str, TokenRecord]
    ) -> None:
        """Persist (merge) `{token: {"value": ..., "category": ...}}` for a document."""

    @abstractmethod
    async def get_mapping(self, document_id: str) -> Dict[str, TokenRecord]:
        """Return the full token map for a document (empty dict if none)."""

    @abstractmethod
    async def get_token(self, document_id: str, token: str) -> Optional[TokenRecord]:
        """Return a single token's record, or None if not found."""

    @abstractmethod
    async def delete_mapping(self, document_id: str) -> None:
        """Remove all stored tokens for a document (e.g. after retention TTL)."""


class InMemoryTokenMappingStore(TokenMappingStore):
    """Default, process-local implementation.

    Suitable for development, tests, and single-worker deployments.
    Swap for a Redis- or database-backed `TokenMappingStore`
    implementation for multi-worker production deployments so token
    maps survive across Celery worker processes.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, TokenRecord]] = {}
        # One lock per document keeps concurrent requests for
        # *different* documents from blocking each other, while still
        # serializing concurrent writers for the *same* document.
        self._locks: Dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()
        self._value_encryptor: Optional[Callable[[str], str]] = None
        self._value_decryptor: Optional[Callable[[str], str]] = None

    def set_encryption(
        self,
        encryptor: Callable[[str], str],
        decryptor: Callable[[str], str],
    ) -> None:
        """Wire in at-rest encryption for stored values (e.g. Fernet via
        `app.core.security.encrypt_phi` / `decrypt_phi`). Optional --
        if never called, values are stored as plain strings in memory."""
        self._value_encryptor = encryptor
        self._value_decryptor = decryptor

    async def _lock_for(self, document_id: str) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(document_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[document_id] = lock
            return lock

    async def save_mapping(
        self, document_id: str, mapping: Dict[str, TokenRecord]
    ) -> None:
        if not mapping:
            return
        try:
            lock = await self._lock_for(document_id)
            async with lock:
                bucket = self._store.setdefault(document_id, {})
                for token, record in mapping.items():
                    value = record["value"]
                    if self._value_encryptor is not None:
                        value = self._value_encryptor(value)
                    bucket[token] = {"value": value, "category": record["category"]}
        except Exception as exc:  # pragma: no cover - defensive
            log.error(
                f"Failed to save PHI token mapping for document "
                f"{document_id}: {exc}", exc_info=True,
            )
            raise TokenMappingStoreError(str(exc)) from exc

    async def get_mapping(self, document_id: str) -> Dict[str, TokenRecord]:
        try:
            lock = await self._lock_for(document_id)
            async with lock:
                bucket = self._store.get(document_id, {})
                if self._value_decryptor is None:
                    return dict(bucket)
                return {
                    token: {
                        "value": self._value_decryptor(record["value"]),
                        "category": record["category"],
                    }
                    for token, record in bucket.items()
                }
        except Exception as exc:  # pragma: no cover - defensive
            log.error(
                f"Failed to read PHI token mapping for document "
                f"{document_id}: {exc}", exc_info=True,
            )
            raise TokenMappingStoreError(str(exc)) from exc

    async def get_token(self, document_id: str, token: str) -> Optional[TokenRecord]:
        try:
            lock = await self._lock_for(document_id)
            async with lock:
                bucket = self._store.get(document_id, {})
                record = bucket.get(token)
                if record is None:
                    return None
                value = record["value"]
                if self._value_decryptor is not None:
                    value = self._value_decryptor(value)
                return {"value": value, "category": record["category"]}
        except Exception as exc:  # pragma: no cover - defensive
            log.error(
                f"Failed to read PHI token '{token}' for document "
                f"{document_id}: {exc}", exc_info=True,
            )
            raise TokenMappingStoreError(str(exc)) from exc

    async def delete_mapping(self, document_id: str) -> None:
        try:
            lock = await self._lock_for(document_id)
            async with lock:
                self._store.pop(document_id, None)
        except Exception as exc:  # pragma: no cover - defensive
            log.error(
                f"Failed to delete PHI token mapping for document "
                f"{document_id}: {exc}", exc_info=True,
            )
            raise TokenMappingStoreError(str(exc)) from exc

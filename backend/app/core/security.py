"""
LMIS Security Utilities
=======================
Provides:
- JWT access / refresh token creation and verification
- Password hashing (bcrypt via passlib)
- PHI tokenization middleware (replaces PII patterns with UUID tokens,
  stores reversible mapping in Redis with configurable TTL)
- Fernet symmetric encryption helpers for at-rest PHI field encryption
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
settings = get_settings()

ALGORITHM = settings.algorithm

import bcrypt

def hash_password(plain_password: str) -> str:
    """Return bcrypt hash of *plain_password*."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_password.encode('utf-8'), salt).decode('utf-8')

get_password_hash = hash_password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return ``True`` if *plain_password* matches *hashed_password*."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


# ─── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Mint a short-lived JWT access token.

    Parameters
    ----------
    subject:
        Typically the user's UUID string.
    extra_claims:
        Additional payload fields (e.g. ``role``).
    """
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str) -> str:
    """Mint a long-lived JWT refresh token."""
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(days=settings.refresh_token_expire_days)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """Decode and validate a JWT token.

    Raises
    ------
    ValueError
        If the token is expired, invalid, or has the wrong type.
    """
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc

    if payload.get("type") != expected_type:
        raise ValueError(
            f"Expected token type '{expected_type}', got '{payload.get('type')}'"
        )
    return payload


# ─── Fernet Encryption ────────────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    """Return a Fernet instance using the configured key.

    Raises
    ------
    RuntimeError
        If ``phi_encryption_key`` is not set or is invalid.
    """
    key = settings.phi_encryption_key
    if not key:
        raise RuntimeError(
            "phi_encryption_key is not configured. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:
        raise RuntimeError(f"Invalid phi_encryption_key: {exc}") from exc


def encrypt_phi(plaintext: str) -> str:
    """Encrypt a PHI string field and return the base64-encoded ciphertext."""
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_phi(ciphertext: str) -> str:
    """Decrypt a PHI ciphertext field and return the plaintext.

    Raises
    ------
    ValueError
        If decryption fails (wrong key or corrupted data).
    """
    fernet = _get_fernet()
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("PHI decryption failed — invalid key or corrupted data") from exc


# ─── PHI Tokenization Middleware ─────────────────────────────────────────────

# Patterns to detect and tokenize before sending text to external LLMs.
# Each pattern maps to a category label used in the token key.
_PHI_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("MRN", re.compile(r"\bMRN[:\s#-]*\d{5,12}\b", re.IGNORECASE)),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("DOB", re.compile(
        r"\b(?:DOB|Date of Birth)[:\s]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        re.IGNORECASE,
    )),
    ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("NAME", re.compile(
        r"\b(?:Patient|Dr\.?|Doctor|Mr\.?|Mrs\.?|Ms\.?|Prof\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b"
    )),
    ("ADDRESS", re.compile(
        r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+(?:St|Ave|Blvd|Rd|Dr|Lane|Ln|Way|Court|Ct)\b",
        re.IGNORECASE,
    )),
    ("NPI", re.compile(r"\bNPI[:\s]*\d{10}\b", re.IGNORECASE)),
    ("ACCESSION", re.compile(r"\b(?:Acc(?:ession)?[#:\s]*)[A-Z0-9]{6,12}\b", re.IGNORECASE)),
]


class PHITokenizer:
    """Reversible PHI tokenizer backed by Redis.

    Replaces detected PHI spans with opaque UUID tokens before the text
    reaches any external LLM API, and restores them afterwards.

    Parameters
    ----------
    redis_client:
        An async Redis client instance.
    ttl_seconds:
        How long to keep the token→original mapping in Redis.
    """

    TOKEN_PREFIX = "phi_token:"

    def __init__(self, redis_client: Any, ttl_seconds: int = 3600) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    async def tokenize(self, text: str) -> tuple[str, dict[str, str]]:
        """Replace PHI spans with UUID tokens.

        Returns
        -------
        tuple[str, dict[str, str]]
            The redacted text and a ``{token: original_value}`` mapping.
        """
        mapping: dict[str, str] = {}
        redacted = text

        for category, pattern in _PHI_PATTERNS:
            for match in reversed(list(pattern.finditer(redacted))):
                original = match.group(0)
                token = f"[PHI_{category}_{uuid4().hex[:8].upper()}]"
                mapping[token] = original

                # Persist mapping in Redis
                redis_key = f"{self.TOKEN_PREFIX}{token}"
                await self._redis.set(redis_key, original, ex=self._ttl)

                redacted = redacted[: match.start()] + token + redacted[match.end():]

        if mapping:
            log.debug(
                "phi_tokenized",
                token_count=len(mapping),
                categories=list({k.split("_")[1] for k in mapping}),
            )

        return redacted, mapping

    async def detokenize(self, text: str, mapping: dict[str, str] | None = None) -> str:
        """Restore PHI tokens to their original values.

        Uses in-memory *mapping* first; falls back to Redis lookup.
        """
        token_pattern = re.compile(r"\[PHI_[A-Z]+_[A-F0-9]{8}\]")
        result = text

        for match in token_pattern.finditer(text):
            token = match.group(0)
            original: str | None = None

            # In-memory lookup first
            if mapping and token in mapping:
                original = mapping[token]
            else:
                # Redis fallback
                redis_key = f"{self.TOKEN_PREFIX}{token}"
                stored = await self._redis.get(redis_key)
                if stored:
                    original = stored if isinstance(stored, str) else stored.decode()

            if original:
                result = result.replace(token, original)
            else:
                log.warning("phi_token_not_found", token=token)

        return result

    async def tokenize_for_llm(self, text: str) -> tuple[str, dict[str, str]]:
        """Convenience wrapper: tokenize only when redaction is enabled."""
        if not settings.phi_redaction_enabled:
            return text, {}
        return await self.tokenize(text)


# ─── Utility ──────────────────────────────────────────────────────────────────

def sha256_hash(data: bytes) -> str:
    """Return hex-encoded SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()

"""
LMIS Custom Exception Hierarchy
================================
All application-level exceptions with HTTP status codes and structured detail.
FastAPI exception handlers convert these to JSON error responses automatically.
"""
from __future__ import annotations

from typing import Any


class LMISException(Exception):
    """Base exception for all LMIS application errors.

    Attributes
    ----------
    status_code:
        HTTP status code that should be returned to the client.
    message:
        Short human-readable error message.
    detail:
        Optional additional structured detail (will be serialised to JSON).
    """

    status_code: int = 500
    message: str = "An internal LMIS error occurred"

    def __init__(
        self,
        message: str | None = None,
        detail: Any | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"status_code={self.status_code}, "
            f"message={self.message!r}, "
            f"detail={self.detail!r})"
        )


# ─── Pipeline Processing Exceptions ──────────────────────────────────────────

class DocumentProcessingError(LMISException):
    """Raised when a document cannot be processed through the pipeline.

    Typically wraps lower-level IOError or file-format problems.
    """

    status_code = 422
    message = "Document processing failed"


class ExtractionError(LMISException):
    """Raised by the OCR or NER agent when text/entity extraction fails.

    Includes the agent name and the span or page that caused the failure.
    """

    status_code = 422
    message = "Entity extraction failed"

    def __init__(
        self,
        message: str | None = None,
        detail: Any | None = None,
        agent: str = "unknown",
        page: int | None = None,
    ) -> None:
        super().__init__(message=message, detail=detail)
        self.agent = agent
        self.page = page


class NormalizationError(LMISException):
    """Raised when a clinical entity cannot be mapped to a canonical code.

    The ``entity_type`` and ``raw_value`` identify the offending entity.
    """

    status_code = 422
    message = "Entity normalization failed"

    def __init__(
        self,
        message: str | None = None,
        detail: Any | None = None,
        entity_type: str = "unknown",
        raw_value: str = "",
    ) -> None:
        super().__init__(message=message, detail=detail)
        self.entity_type = entity_type
        self.raw_value = raw_value


class ReasoningError(LMISException):
    """Raised by the ReasoningAgent when clinical insight generation fails.

    Covers both LLM-call failures and cases where the model's structured
    output could not be safely reconciled with the evidence pool it was
    given (e.g. every candidate cited unknown evidence_ids).
    """

    status_code = 422
    message = "Clinical reasoning failed"

    def __init__(
        self,
        message: str | None = None,
        detail: Any | None = None,
        patient_id: str = "",
    ) -> None:
        super().__init__(message=message, detail=detail)
        self.patient_id = patient_id


class VerificationError(LMISException):
    """Raised by the VerificationAgent when an insight cannot be verified.

    Includes the draft_id that triggered the error.
    """

    status_code = 422
    message = "Insight verification failed"

    def __init__(
        self,
        message: str | None = None,
        detail: Any | None = None,
        draft_id: str = "",
    ) -> None:
        super().__init__(message=message, detail=detail)
        self.draft_id = draft_id


class KnowledgeRetrievalError(LMISException):
    """Raised by the KnowledgeAgent when clinical knowledge retrieval fails.

    Covers vector-store/embedding-backend failures. Deliberately NOT raised
    for "no results found" -- an empty retrieval is a valid outcome handled
    gracefully by the agent, not an error condition.
    """

    status_code = 502
    message = "Clinical knowledge retrieval failed"

    def __init__(
        self,
        message: str | None = None,
        detail: Any | None = None,
        patient_id: str = "",
    ) -> None:
        super().__init__(message=message, detail=detail)
        self.patient_id = patient_id


class EscalationError(LMISException):
    """Raised when an insight requiring clinician review cannot be escalated.

    For example, if the clinician review queue is full or the notification
    service is unreachable.
    """

    status_code = 503
    message = "Clinician escalation failed"


# ─── Storage Exceptions ───────────────────────────────────────────────────────

class StorageError(LMISException):
    """Raised by the StorageService for MinIO / object-store failures.

    Includes the bucket name and object key that caused the problem.
    """

    status_code = 503
    message = "Object storage operation failed"

    def __init__(
        self,
        message: str | None = None,
        detail: Any | None = None,
        bucket: str = "",
        key: str = "",
    ) -> None:
        super().__init__(message=message, detail=detail)
        self.bucket = bucket
        self.key = key


# ─── Auth Exceptions ──────────────────────────────────────────────────────────

class AuthError(LMISException):
    """Raised for authentication and authorisation failures.

    Maps to HTTP 401 (unauthenticated) or 403 (forbidden) depending on context.
    """

    status_code = 401
    message = "Authentication failed"


class InsufficientPermissionsError(AuthError):
    """Raised when an authenticated user lacks the required role."""

    status_code = 403
    message = "Insufficient permissions"


class TokenExpiredError(AuthError):
    """Raised when a JWT token has expired."""

    status_code = 401
    message = "Token has expired"


# ─── Data Validation Exceptions ───────────────────────────────────────────────

class SchemaValidationError(LMISException):
    """Raised when inter-agent message schemas fail Pydantic validation."""

    status_code = 422
    message = "Agent message schema validation failed"


class ConflictError(LMISException):
    """Raised on duplicate record creation (e.g. duplicate patient upload)."""

    status_code = 409
    message = "Resource conflict"


class NotFoundError(LMISException):
    """Raised when a requested resource does not exist."""

    status_code = 404
    message = "Resource not found"
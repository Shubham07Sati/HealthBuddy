"""
LMIS Core Configuration
=======================
Pydantic Settings class that reads all environment variables from .env file.
Uses @lru_cache for singleton pattern.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.key_management import ensure_phi_encryption_key, is_valid_fernet_key

# Ensure a PHI_ENCRYPTION_KEY is available (local dev only; never
# overwrites an existing key) *before* Settings reads the environment /
# .env file below. See app.core.key_management for the full contract.
ensure_phi_encryption_key()


class Settings(BaseSettings):
    """Central configuration for the LMIS application.

    All values can be overridden by environment variables or a .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ───────────────────────────────────────────────────────────────────
    app_name: str = Field(default="LMIS", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development"
    )
    debug: bool = Field(default=False)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )

    # ─── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://lmis:lmis_secret@localhost:5432/lmis_db"
    )

    # ─── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ─── Celery ────────────────────────────────────────────────────────────────
    celery_broker_url: str = Field(default="redis://localhost:6379/1")
    celery_result_backend: str = Field(default="redis://localhost:6379/2")

    # ─── MinIO ─────────────────────────────────────────────────────────────────
    minio_endpoint: str = Field(default="localhost:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin")
    minio_bucket_documents: str = Field(default="lmis-documents")
    minio_bucket_ocr: str = Field(default="lmis-ocr-output")
    minio_secure: bool = Field(default=False)

    # ─── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str | None = Field(default=None)
    qdrant_collection_knowledge: str = Field(default="lmis_knowledge")
    qdrant_collection_patient_prefix: str = Field(default="lmis_patient_")

    # ─── LLM Providers ─────────────────────────────────────────────────────────
    llm_provider: Literal["anthropic", "openai", "google", "ollama"] = Field(
        default="openai"
    )
    anthropic_api_key: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o")
    google_api_key: str | None = Field(default=None)
    google_model: str = Field(default="gemini-1.5-pro")
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.1:8b")

    # ─── Model role assignments ─────────────────────────────────────────────────
    generator_model: str = Field(
        default="gpt-4o",
        description="Model used by ReasoningAgent to draft insights",
    )
    verifier_model: str = Field(
        default="gpt-4o",
        description="Model used by VerificationAgent to critique insights",
    )
    fast_model: str = Field(
        default="gpt-4o-mini",
        description="Smaller/cheaper model for decomposition tasks",
    )

    # ─── Auth / JWT ────────────────────────────────────────────────────────────
    secret_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_USE_32_CHAR_SECRET_KEY_MINIMUM"
    )
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)
    refresh_token_expire_days: int = Field(default=7)

    # ─── PHI / Encryption ──────────────────────────────────────────────────────
    phi_redaction_enabled: bool = Field(default=True)
    phi_encryption_key: str = Field(
        default="",
        description="Fernet-compatible base64 key for PHI field encryption",
    )

    # ─── Confidence Thresholds ─────────────────────────────────────────────────
    ocr_confidence_threshold: float = Field(default=0.70)
    ner_confidence_threshold: float = Field(default=0.65)
    ontology_match_threshold: float = Field(default=0.80)

    # ─── Statistical / Business Rules ──────────────────────────────────────────
    trend_min_data_points: int = Field(
        default=3, description="Minimum data points for trend computation"
    )
    retrieval_similarity_threshold: float = Field(
        default=0.75, description="Minimum cosine similarity to return a result"
    )

    # ─── Reasoning Agent ───────────────────────────────────────────────────────
    reasoning_max_insights: int = Field(
        default=8, description="Maximum number of draft insights the Reasoning Agent will emit per run"
    )
    reasoning_min_confidence: float = Field(
        default=0.55, description="Draft insights below this confidence are discarded before verification"
    )
    reasoning_min_evidence_relevance: float = Field(
        default=0.5, description="Evidence items below this relevance score are excluded from the reasoning context"
    )

    # ─── CORS ──────────────────────────────────────────────────────────────────
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"]
    )

    # ─── Embeddings ────────────────────────────────────────────────────────────
    embedding_model_general: str = Field(default="all-MiniLM-L6-v2")
    embedding_model_biomedical: str = Field(
        default="pritamdeka/S-PubMedBert-MS-MARCO"
    )
    embedding_dimension: int = Field(default=768)
    embedding_use_biomedical_model: bool = Field(default=True)

    # ─── Knowledge Agent (Agent 8) ──────────────────────────────────────────────
    knowledge_top_k: int = Field(default=8)
    knowledge_max_results: int = Field(default=10)
    knowledge_min_relevance: float = Field(default=0.5)
    knowledge_max_query_terms: int = Field(default=6)

    # ─── Validators ────────────────────────────────────────────────────────────
    @field_validator("ocr_confidence_threshold", "ner_confidence_threshold",
                     "ontology_match_threshold", "retrieval_similarity_threshold",
                     mode="before")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        """Ensure all confidence thresholds are in [0, 1]."""
        v = float(v)
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Threshold must be between 0 and 1, got {v}")
        return v

    @field_validator("trend_min_data_points", mode="before")
    @classmethod
    def validate_min_points(cls, v: int) -> int:
        v = int(v)
        if v < 2:
            raise ValueError("trend_min_data_points must be at least 2")
        return v

    @field_validator("phi_encryption_key")
    @classmethod
    def validate_phi_encryption_key_format(cls, v: str) -> str:
        """If a PHI_ENCRYPTION_KEY value is present, it must be a
        structurally valid Fernet key. An empty value is allowed here
        (e.g. a production deployment mid-provisioning); the explicit
        validate_phi_encryption_key startup check is what enforces
        that it is actually present before the app serves traffic.
        This never logs or includes the key value itself.
        """
        if v and not is_valid_fernet_key(v):
            raise ValueError(
                "PHI_ENCRYPTION_KEY is set but is not a valid Fernet key. "
                "Never hand-craft this value -- generate one with "
                "Fernet.generate_key() (or let the local dev bootstrap in "
                "app.core.key_management do it for you) and never commit "
                "it to version control."
            )
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()


# Convenience alias used throughout the application
settings: Settings = get_settings()


def validate_phi_encryption_key(settings_obj: "Settings | None" = None) -> None:
    """Fail fast with a clear, actionable error if PHI_ENCRYPTION_KEY is
    missing or invalid.

    Intended to be called once during application startup (see the
    lifespan handler in app.main) so a misconfigured key is caught
    before the app serves any traffic, rather than surfacing later as
    an opaque error the first time PHI encryption is used.

    Never logs, prints, or otherwise includes the key's value.
    """
    s = settings_obj or get_settings()

    if not s.phi_encryption_key:
        raise RuntimeError(
            "PHI_ENCRYPTION_KEY is not configured. For local development, "
            "one is generated automatically on startup and stored in your "
            "local .env file -- if you still see this, check that .env is "
            "writable. In staging/production, provision this value via "
            "your secrets manager; it must never be committed to version "
            "control."
        )

    if not is_valid_fernet_key(s.phi_encryption_key):
        # Field validation above should already catch this, but this stays
        # as cheap insurance for any path that bypasses Settings
        # validation (e.g. a value swapped in after construction).
        raise RuntimeError(
            "PHI_ENCRYPTION_KEY is set but is not a valid Fernet key. "
            "Regenerate it -- never hand-edit this value."
        )
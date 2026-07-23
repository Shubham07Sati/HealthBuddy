import uuid
import enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Float, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from .base import Base

class InsightVerificationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    modified = "modified"
    unverified_informational = "unverified_informational"

class InsightSeverity(str, enum.Enum):
    informational = "informational"
    low = "low"
    moderate = "moderate"
    high = "high"
    critical = "critical"

class ClinicianAction(str, enum.Enum):
    approved = "approved"
    rejected = "rejected"
    modified = "modified"

class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    
    draft_text: Mapped[str] = mapped_column(String, nullable=False)
    final_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    supporting_entity_ids: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    supporting_evidence_ids: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    
    model_inference_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    
    verification_status: Mapped[InsightVerificationStatus] = mapped_column(SQLEnum(InsightVerificationStatus), default=InsightVerificationStatus.pending)
    verification_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verification_rationale: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rejected_assertions: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    
    severity: Mapped[InsightSeverity] = mapped_column(SQLEnum(InsightSeverity), default=InsightSeverity.informational)
    
    requires_clinician_review: Mapped[bool] = mapped_column(Boolean, default=False)
    clinician_reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    clinician_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    clinician_action: Mapped[Optional[ClinicianAction]] = mapped_column(SQLEnum(ClinicianAction), nullable=True)
    
    patient_facing_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    clinician_facing_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)

import uuid
import enum
from datetime import datetime
from typing import Optional, Any, Dict
from sqlalchemy import String, Float, Boolean, DateTime, Integer, Index, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from .base import Base

class EntityType(str, enum.Enum):
    medication = "medication"
    lab_value = "lab_value"
    diagnosis = "diagnosis"
    procedure = "procedure"
    vital_sign = "vital_sign"
    date = "date"
    body_site = "body_site"
    dosage = "dosage"
    frequency = "frequency"
    unit = "unit"
    other = "other"

class AssertionStatus(str, enum.Enum):
    present = "present"
    absent = "absent"
    possible = "possible"
    conditional = "conditional"
    hypothetical = "hypothetical"

class VerificationStatus(str, enum.Enum):
    auto_verified = "auto_verified"
    unverified = "unverified"
    human_corrected = "human_corrected"
    flagged = "flagged"

class ClinicalEntity(Base):
    __tablename__ = "clinical_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    
    entity_type: Mapped[EntityType] = mapped_column(SQLEnum(EntityType), nullable=False)
    
    raw_value: Mapped[str] = mapped_column(String(1024), nullable=False)
    entity_label: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # human-readable name, e.g. "Hemoglobin"
    normalized_value: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    unit_raw: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    unit_canonical: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    canonical_code: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    coding_system: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    ocr_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    ner_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    
    source_span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    source_span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    source_bounding_box: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    entity_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_negated: Mapped[bool] = mapped_column(Boolean, default=False)
    assertion_status: Mapped[AssertionStatus] = mapped_column(SQLEnum(AssertionStatus), default=AssertionStatus.present)
    verification_status: Mapped[VerificationStatus] = mapped_column(SQLEnum(VerificationStatus), default=VerificationStatus.unverified)
    
    reference_range_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reference_range_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reference_range_unit: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index('ix_patient_type_date', 'patient_id', 'entity_type', 'entity_date'),
    )

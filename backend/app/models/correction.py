import uuid
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from .base import Base

class CorrectionType(str, enum.Enum):
    ocr_error = "ocr_error"
    ner_error = "ner_error"
    normalization_error = "normalization_error"
    unit_error = "unit_error"
    date_error = "date_error"
    false_positive = "false_positive"
    other = "other"

class CorrectionStatus(str, enum.Enum):
    pending = "pending"
    in_review = "in_review"
    corrected = "corrected"
    dismissed = "dismissed"

class CorrectionQueueItem(Base):
    __tablename__ = "correction_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    
    correction_type: Mapped[CorrectionType] = mapped_column(SQLEnum(CorrectionType), nullable=False)
    original_value: Mapped[str] = mapped_column(String(1024), nullable=False)
    suggested_correction: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    
    status: Mapped[CorrectionStatus] = mapped_column(SQLEnum(CorrectionStatus), default=CorrectionStatus.pending)
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

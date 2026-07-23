import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from .base import Base
import enum

class DocumentType(str, enum.Enum):
    typed_pdf = "typed_pdf"
    scanned_image = "scanned_image"
    handwritten = "handwritten"
    lab_report = "lab_report"
    imaging_report = "imaging_report"
    discharge_summary = "discharge_summary"
    unknown = "unknown"

class ProcessingStatus(str, enum.Enum):
    queued = "queued"
    ingesting = "ingesting"
    ocr = "ocr"
    ner = "ner"
    normalizing = "normalizing"
    trend_analysis = "trend_analysis"
    reasoning = "reasoning"
    verifying = "verifying"
    complete = "complete"
    failed = "failed"
    needs_rescan = "needs_rescan"

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(SQLEnum(DocumentType), default=DocumentType.unknown)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    ocr_storage_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    
    processing_status: Mapped[ProcessingStatus] = mapped_column(SQLEnum(ProcessingStatus), default=ProcessingStatus.queued)
    pipeline_job_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    document_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_facility: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # patient = relationship("Patient", back_populates="documents")
    # clinical_entities = relationship("ClinicalEntity", back_populates="document")

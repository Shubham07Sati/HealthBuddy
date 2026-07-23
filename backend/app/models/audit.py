import uuid
import enum
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Float, DateTime, Enum as SQLEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, UUID
from .base import Base

class AuditStatus(str, enum.Enum):
    success = "success"
    failure = "failure"
    partial = "partial"

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    
    input_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    model_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    
    status: Mapped[AuditStatus] = mapped_column(SQLEnum(AuditStatus), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    
    metadata_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

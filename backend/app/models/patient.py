import uuid
from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import String, Date, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from .base import Base

class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    sex: Mapped[str] = mapped_column(String(50), nullable=False)
    blood_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    known_conditions: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    known_medications: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    allergies: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    phi_encryption_key_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    user = relationship("User", back_populates="patient_profile")
    # documents = relationship("Document", back_populates="patient")
    # clinical_entities = relationship("ClinicalEntity", back_populates="patient")
    # trends = relationship("Trend", back_populates="patient")
    # insights = relationship("Insight", back_populates="patient")

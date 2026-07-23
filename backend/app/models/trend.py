import uuid
import enum
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Float, Boolean, DateTime, Integer, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from .base import Base

class TrendDirection(str, enum.Enum):
    increasing = "increasing"
    decreasing = "decreasing"
    stable = "stable"
    insufficient_data = "insufficient_data"

class Trend(Base):
    __tablename__ = "trends"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_canonical_code: Mapped[str] = mapped_column(String(255), nullable=False)
    
    direction: Mapped[TrendDirection] = mapped_column(SQLEnum(TrendDirection), nullable=False)
    rate_of_change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    trend_start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trend_end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    data_point_count: Mapped[int] = mapped_column(Integer, nullable=False)
    statistical_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    p_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    change_point_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    is_clinically_significant: Mapped[bool] = mapped_column(Boolean, default=False)
    clinical_significance_reason: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    
    trend_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from app.models.document import ProcessingStatus
from app.models.correction import CorrectionType, CorrectionStatus
from app.models.insight import ClinicianAction
from .agent_messages import TrendObject, VerifiedInsight
from .common import PaginatedResponse

class DocumentUploadResponse(BaseModel):
    document_id: UUID
    job_id: str
    filename: str
    status: ProcessingStatus
    message: str

class PipelineStatusResponse(BaseModel):
    document_id: UUID
    status: ProcessingStatus
    current_step: str
    progress_percentage: int
    error_message: Optional[str] = None

class TimelineResponse(PaginatedResponse[Dict[str, Any]]):
    pass

class InsightListResponse(PaginatedResponse[VerifiedInsight]):
    pass

class CorrectionRequest(BaseModel):
    suggested_correction: str
    notes: Optional[str] = None

class CorrectionResponse(BaseModel):
    id: UUID
    entity_id: UUID
    correction_type: CorrectionType
    status: CorrectionStatus
    message: str

class ClinicianReviewRequest(BaseModel):
    action: ClinicianAction
    modified_text: Optional[str] = None
    notes: Optional[str] = None

class AuditLogResponse(PaginatedResponse[Dict[str, Any]]):
    pass

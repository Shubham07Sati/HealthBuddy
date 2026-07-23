from uuid import UUID
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel
from app.models.document import DocumentType
from app.models.clinical_entity import EntityType, AssertionStatus, VerificationStatus
from app.models.trend import TrendDirection
from app.models.insight import InsightSeverity
from .common import BoundingBox

class DocumentEnvelope(BaseModel):
    document_id: UUID
    patient_id: UUID
    storage_path: str
    document_type: DocumentType
    quality_score: float
    quality_flags: List[str]
    routing: Literal["ocr", "handwriting_ocr", "reject"]
    rejection_reason: Optional[str] = None
    metadata: Dict[str, Any]

class TextSpan(BaseModel):
    text: str
    confidence: float
    bounding_box: Optional[BoundingBox] = None
    page: int
    span_type: Literal["text", "table_cell", "form_field", "header", "handwriting"]

class DetectedTable(BaseModel):
    page: int
    bounding_box: BoundingBox
    headers: List[str]
    rows: List[List[str]]
    confidence: float

class RawExtraction(BaseModel):
    document_id: UUID
    spans: List[TextSpan]
    tables: List[DetectedTable]
    full_text: str
    avg_confidence: float
    low_confidence_spans: List[TextSpan]
    ocr_engine: str
    processing_time_ms: int

class ExtractedEntity(BaseModel):
    temp_id: str
    entity_type: EntityType
    raw_value: str
    entity_label: Optional[str] = None
    unit_raw: Optional[str] = None
    entity_date: Optional[datetime] = None
    source_span_start: int
    source_span_end: int
    source_bounding_box: Optional[BoundingBox] = None
    ocr_confidence: float
    ner_confidence: float
    combined_confidence: float
    is_negated: bool
    assertion_status: AssertionStatus
    related_entities: List[str]
    ambiguity_flag: bool
    ambiguity_reason: Optional[str] = None

class ClinicalEntitySet(BaseModel):
    document_id: UUID
    patient_id: UUID
    entities: List[ExtractedEntity]
    intra_document_conflicts: List[Dict[str, Any]]
    processing_time_ms: int

class CodedEntity(BaseModel):
    temp_id: str
    entity_db_id: Optional[UUID] = None
    canonical_code: Optional[str] = None
    coding_system: Optional[str] = None
    normalized_value: str
    unit_canonical: Optional[str] = None
    reference_range_low: Optional[float] = None
    reference_range_high: Optional[float] = None
    reference_range_unit: Optional[str] = None
    coding_confidence: float
    coding_method: Literal["exact", "fuzzy", "llm_assisted", "unmatched"]

class CodedEntitySet(BaseModel):
    document_id: UUID
    patient_id: UUID
    coded_entities: List[CodedEntity]
    unmatched_entities: List[ExtractedEntity]
    processing_time_ms: int

class TrendDataPoint(BaseModel):
    entity_id: UUID
    value: float
    unit: str
    timestamp: datetime
    confidence: float
    document_id: UUID

class TrendObject(BaseModel):
    metric_name: str
    metric_canonical_code: str
    data_points: List[TrendDataPoint]
    direction: TrendDirection
    rate_of_change: Optional[float] = None
    statistical_confidence: float
    p_value: Optional[float] = None
    change_point_date: Optional[datetime] = None
    is_clinically_significant: bool
    clinical_significance_reason: Optional[str] = None
    monitoring_gap_detected: bool
    expected_monitoring_interval_days: Optional[int] = None
    last_measurement_date: Optional[datetime] = None
    absolute_change: Optional[float] = None
    percentage_change: Optional[float] = None
    threshold_crossings: List[Dict[str, Any]] = []
    abnormal_persistence: bool = False
    clinical_trend: Optional[str] = None

class TrendSet(BaseModel):
    patient_id: UUID
    trends: List[TrendObject]
    gaps: List[Dict[str, Any]]
    insufficient_data_metrics: List[str]
    processing_time_ms: int

class KnowledgeItem(BaseModel):
    guideline_id: str
    title: str
    source: str
    section: Optional[str] = None
    text: str
    relevance_score: float
    category: str
    citation: str
    reference_range_low: Optional[float] = None
    reference_range_high: Optional[float] = None
    reference_range_unit: Optional[str] = None
    retrieval_query: str

class EvidenceItem(BaseModel):
    evidence_id: str
    source_type: Literal["pso_entity", "retrieved_passage", "guideline"]
    source_ref: str
    text: str
    relevance_score: float

class DraftInsight(BaseModel):
    draft_id: str
    text: str
    supporting_entity_ids: List[UUID]
    supporting_evidence_ids: List[str]
    model_inference_flag: bool
    severity: InsightSeverity
    patient_facing_text: str
    clinician_facing_text: str
    insight_type: Literal["trend", "gap", "medication", "diagnosis", "risk_flag", "general"]

class DraftInsightSet(BaseModel):
    patient_id: UUID
    insights: List[DraftInsight]
    evidence_used: List[EvidenceItem]
    generator_model: str
    processing_time_ms: int

class AtomicAssertion(BaseModel):
    assertion_text: str
    verified: bool
    supporting_evidence: List[EvidenceItem]
    contradicting_evidence: List[EvidenceItem]
    confidence: float

class VerifiedInsight(BaseModel):
    draft_id: str
    insight_db_id: Optional[UUID] = None
    final_text: str
    patient_facing_text: str
    clinician_facing_text: str
    verification_status: VerificationStatus
    verification_confidence: float
    verification_rationale: str
    atomic_assertions: List[AtomicAssertion]
    rejected_assertions: List[AtomicAssertion]
    severity: InsightSeverity
    requires_clinician_review: bool

class VerifiedInsightSet(BaseModel):
    patient_id: UUID
    verified_insights: List[VerifiedInsight]
    rejected_insights: List[DraftInsight]
    verifier_model: str
    processing_time_ms: int

class PatientStateObject(BaseModel):
    patient_id: UUID
    documents: List[Dict[str, Any]]
    entities: List[Dict[str, Any]]
    trends: List[TrendObject]
    insights: List[Dict[str, Any]]
    last_updated: datetime

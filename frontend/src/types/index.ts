// ============================================================
// HealthBuddy — All TypeScript Types & Interfaces
// ============================================================

// ---------- Auth ----------
export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  created_at: string;
  last_login?: string;
  is_active: boolean;
  avatar_url?: string;
}

export type UserRole = 'patient' | 'clinician' | 'admin';

// Alias used by API client — identical to User
export type UserResponse = User;

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: User;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  full_name: string;
  email: string;
  password: string;
  role: UserRole;
}

// ---------- Documents ----------
export type DocumentStatus =
  | 'queued'
  | 'processing'
  | 'complete'
  | 'failed'
  | 'needs_rescan';

export type DocumentType =
  | 'lab_report'
  | 'clinical_note'
  | 'prescription'
  | 'imaging_report'
  | 'discharge_summary'
  | 'referral_letter'
  | 'unknown';

export interface Document {
  id: string;
  patient_id: string;
  filename: string;
  file_type: string;
  document_type: DocumentType;
  status: DocumentStatus;
  uploaded_at: string;
  processed_at?: string;
  page_count?: number;
  entity_count?: number;
  size_bytes: number;
  error_message?: string;
  thumbnail_url?: string;
}

export interface DocumentUploadResponse {
  document_id: string;
  job_id: string;
  filename: string;
  status: DocumentStatus;
  message: string;
}

// ---------- Pipeline ----------
export type PipelineStepStatus = 'pending' | 'running' | 'complete' | 'failed' | 'skipped';

export interface PipelineStep {
  name: string;
  label: string;
  status: PipelineStepStatus;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  error?: string;
  metadata?: Record<string, unknown>;
}

export interface PipelineStatusResponse {
  job_id: string;
  document_id: string;
  overall_status: DocumentStatus;
  steps: PipelineStep[];
  progress_pct: number;
  current_step: string;
  created_at: string;
  updated_at: string;
  error?: string;
}

export interface WebSocketMessage {
  type: 'status_update' | 'step_complete' | 'complete' | 'error' | 'ping';
  job_id: string;
  step?: string;
  status?: PipelineStepStatus;
  progress_pct?: number;
  pipeline?: PipelineStatusResponse;
  error?: string;
  timestamp: string;
}

// ---------- Clinical Entities ----------
export type EntityType =
  | 'medication'
  | 'lab_value'
  | 'diagnosis'
  | 'procedure'
  | 'vital_sign'
  | 'symptom'
  | 'allergy'
  | 'immunization'
  | 'social_history'
  | 'family_history';

export type AssertionStatus = 'present' | 'absent' | 'possible' | 'conditional' | 'hypothetical';

export interface NormalizedConcept {
  system: string;
  code: string;
  display: string;
}

export interface BoundingBox {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ClinicalEntity {
  id: string;
  document_id: string;
  patient_id: string;
  entity_type: EntityType;
  raw_text: string;
  normalized_text: string;
  value?: number | string;
  unit?: string;
  date_mentioned?: string;
  date_extracted?: string;
  assertion_status: AssertionStatus;
  confidence: number;
  normalized_concept?: NormalizedConcept;
  bounding_box?: BoundingBox;
  context_text?: string;
  page_number?: number;
  created_at: string;
  source_document?: string;
}

// ---------- Trends ----------
export type TrendDirection = 'improving' | 'worsening' | 'stable' | 'insufficient_data';
export type TrendSeverity = 'normal' | 'borderline' | 'abnormal' | 'critical';

export interface TrendDataPoint {
  date: string;
  value: number;
  unit?: string;
  document_id?: string;
  confidence: number;
}

export interface Trend {
  id: string;
  patient_id: string;
  metric_name: string;
  metric_display: string;
  entity_type: EntityType;
  normalized_concept?: NormalizedConcept;
  data_points: TrendDataPoint[];
  direction: TrendDirection;
  severity: TrendSeverity;
  slope?: number;
  reference_range_low?: number;
  reference_range_high?: number;
  unit?: string;
  latest_value?: number;
  previous_value?: number;
  percent_change?: number;
  first_date?: string;
  last_date?: string;
  data_point_count: number;
  last_measured_at?: string;
  expected_interval_days?: number;
  days_overdue?: number;
}

export interface TrendSet {
  patient_id: string;
  trends: Trend[];
  generated_at: string;
}

// ---------- Insights ----------
export type InsightSeverity = 'informational' | 'low' | 'moderate' | 'high' | 'critical';
export type VerificationStatus = 'verified' | 'unverified' | 'pending_review' | 'rejected' | 'modified';
export type InsightStatus = 'approved' | 'pending' | 'unverified' | 'flagged';

export interface AtomicAssertion {
  id: string;
  claim_text: string;
  is_supported: boolean;
  confidence: number;
  evidence_entity_ids: string[];
  verification_note?: string;
}

export interface EvidencePassage {
  id: string;
  text: string;
  source: string;
  relevance_score: number;
  document_id?: string;
  page_number?: number;
}

export interface Insight {
  id: string;
  patient_id: string;
  severity: InsightSeverity;
  headline: string;
  patient_text: string;
  clinician_text: string;
  verification_status: VerificationStatus;
  insight_status: InsightStatus;
  confidence: number;
  verification_rationale?: string;
  supporting_entity_ids: string[];
  supporting_entities?: ClinicalEntity[];
  evidence_passages: EvidencePassage[];
  atomic_assertions: AtomicAssertion[];
  reviewer_id?: string;
  reviewer_notes?: string;
  reviewed_at?: string;
  created_at: string;
  updated_at: string;
  trend_ids?: string[];
}

export interface InsightListResponse {
  insights: Insight[];
  total: number;
  page: number;
  per_page: number;
}

// ---------- Patient ----------
export interface Patient {
  id: string;
  full_name: string;
  date_of_birth: string;
  gender: 'male' | 'female' | 'other' | 'unknown';
  mrn?: string;
  clinician_id?: string;
  created_at: string;
  last_upload_at?: string;
  document_count: number;
  active_insight_count: number;
  pending_review_count: number;
}

export interface PatientSummary {
  patient?: Patient;
  health_score?: number;
  health_trend?: TrendDirection;
  active_medications: number;
  tracked_metrics: number;
  document_count: number;
  pending_reviews: number;
  last_upload?: string;
  monitoring_gaps?: MonitoringGap[];
  recent_insights?: any[];
  top_trends?: Trend[];
  recent_documents?: Document[];
}

export interface MonitoringGap {
  metric_name: string;
  metric_display: string;
  last_measured_at?: string;
  days_since_last: number;
  expected_interval_days: number;
  severity: 'low' | 'moderate' | 'high' | 'critical';
}

// ---------- Timeline ----------
export interface TimelineEvent {
  id: string;
  date: string;
  entity: ClinicalEntity;
  month_key: string; // "2024-03"
}

export interface TimelineGroup {
  month_key: string;
  label: string; // "March 2024"
  events: TimelineEvent[];
}

export interface TimelineResponse {
  patient_id: string;
  groups: TimelineGroup[];
  total_events: number;
  filters_applied: Record<string, unknown>;
}

// ---------- Corrections ----------
export type CorrectionStatus = 'pending' | 'in_review' | 'resolved' | 'dismissed';

export interface CorrectionQueueItem {
  id: string;
  entity_id: string;
  entity: ClinicalEntity;
  original_value: string;
  suggested_canonical: string;
  corrected_value?: string;
  confidence: number;
  correction_type: string;
  status: CorrectionStatus;
  created_at: string;
  resolved_at?: string;
  resolver_id?: string;
  notes?: string;
}

// ---------- Audit ----------
export type AuditEventStatus = 'success' | 'failed' | 'partial';

export interface AuditEvent {
  id: string;
  timestamp: string;
  agent: string;
  action: string;
  patient_id?: string;
  document_id?: string;
  job_id?: string;
  model?: string;
  confidence?: number;
  duration_ms?: number;
  status: AuditEventStatus;
  input_hash?: string;
  output_hash?: string;
  metadata?: Record<string, unknown>;
  error?: string;
}

// ---------- Review Queue ----------
export interface ReviewQueueItem {
  id: string;
  insight: Insight;
  patient: Patient;
  priority: number;
  assigned_to?: string;
  created_at: string;
}

export interface ReviewQueueResponse {
  items: ReviewQueueItem[];
  total: number;
  urgent_count: number;
}

// ---------- API / UI State ----------
export interface ApiError {
  message: string;
  status: number;
  detail?: string | Record<string, unknown>;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  has_next: boolean;
}

export interface UploadProgress {
  file_name: string;
  progress: number;
  status: 'idle' | 'uploading' | 'complete' | 'error';
  error?: string;
  document_id?: string;
  job_id?: string;
}

export interface FilterParams {
  page?: number;
  per_page?: number;
  start_date?: string;
  end_date?: string;
  entity_type?: EntityType[];
  severity?: InsightSeverity[];
  status?: string;
  search?: string;
  confidence_min?: number;
}

// ---------- Navigation ----------
export interface NavItem {
  label: string;
  href: string;
  icon: string;
  roles?: UserRole[];
  badge?: number;
  exact?: boolean;
}

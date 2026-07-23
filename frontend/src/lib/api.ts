import { UserResponse, DocumentUploadResponse, PipelineStatusResponse, TimelineResponse, TrendSet, InsightListResponse, PatientSummary, ReviewQueueResponse, Patient, CorrectionQueueItem, AuditEvent } from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_V1 = `${API_BASE}/api/v1`;

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function fetchApi<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers = new Headers(options.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (!options.body || typeof options.body === 'string') {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(`${API_V1}${endpoint}`, { ...options, headers });
  
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = data.detail || (Array.isArray(data.detail) ? data.detail.map((e: any) => e.msg).join(', ') : msg);
    } catch {}
    throw new ApiError(res.status, msg);
  }
  
  // Handle empty responses (e.g. 204 No Content)
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text);
}

export const authApi = {
  login: async (email: string, password: string) => {
    const params = new URLSearchParams();
    params.append('username', email);
    params.append('password', password);
    
    const res = await fetch(`${API_V1}/auth/login`, {
      method: 'POST',
      body: params,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });
    if (!res.ok) {
      let msg = 'Login failed';
      try {
        const data = await res.json();
        msg = data.detail || msg;
      } catch {}
      throw new ApiError(res.status, msg);
    }
    const data = await res.json();
    if (typeof window !== 'undefined') {
      localStorage.setItem('token', data.access_token);
    }
    return data;
  },
  register: (data: any) => fetchApi<UserResponse>('/auth/register', { method: 'POST', body: JSON.stringify(data) }),
  me: () => fetchApi<UserResponse>('/auth/me'),
  logout: async () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('token');
    }
  }
};

export const documentsApi = {
  upload: async (files: File[], patientId: string) => {
    const formData = new FormData();
    files.forEach(f => formData.append('files', f));
    formData.append('patient_id', patientId);
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    const headers = new Headers();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const res = await fetch(`${API_V1}/documents/upload`, {
      method: 'POST',
      body: formData,
      headers
    });
    if (!res.ok) {
      let msg = res.statusText;
      try { const d = await res.json(); msg = d.detail || msg; } catch {}
      throw new ApiError(res.status, msg);
    }
    return res.json() as Promise<DocumentUploadResponse[]>;
  },
  getStatus: (documentId: string) => fetchApi<PipelineStatusResponse>(`/documents/${documentId}/status`),
  list: (patientId: string) => fetchApi<any[]>(`/patients/${patientId}/documents`),
  delete: (documentId: string) => fetchApi<void>(`/documents/${documentId}`, { method: 'DELETE' })
};

export const patientsApi = {
  getTimeline: (patientId: string, params?: URLSearchParams) => fetchApi<TimelineResponse>(`/patients/${patientId}/timeline?${params?.toString() || ''}`),
  getTrends: (patientId: string) => fetchApi<TrendSet>(`/patients/${patientId}/trends`),
  getInsights: (patientId: string) => fetchApi<InsightListResponse>(`/patients/${patientId}/insights`),
  getSummary: (patientId: string) => fetchApi<PatientSummary>(`/patients/${patientId}/summary`)
};

export const clinicianApi = {
  getReviewQueue: () => fetchApi<ReviewQueueResponse>('/clinician/review-queue'),
  reviewInsight: (insightId: string, action: string, notes?: string) => fetchApi<void>(`/clinician/review/${insightId}`, { method: 'POST', body: JSON.stringify({ action, notes }) }),
  getPatients: () => fetchApi<Patient[]>('/clinician/patients')
};

export const correctionsApi = {
  list: () => fetchApi<CorrectionQueueItem[]>('/corrections'),
  submit: (entityId: string, data: any) => fetchApi<void>(`/corrections/${entityId}`, { method: 'POST', body: JSON.stringify(data) }),
  resolve: (itemId: string, data: any) => fetchApi<void>(`/corrections/${itemId}/resolve`, { method: 'PUT', body: JSON.stringify(data) })
};

export const auditApi = {
  list: (patientId?: string, filters?: any) => fetchApi<AuditEvent[]>('/audit')
};

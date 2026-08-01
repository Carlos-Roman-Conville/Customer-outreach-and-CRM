const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  me: () => request<{ id: number; name: string; email: string; role: string; demo_mode: boolean }>('/me'),
  stats: () => request<Record<string, unknown>>('/stats'),
  queue: (params?: { limit?: number; west?: number; south?: number; east?: number; north?: number }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set('limit', String(params.limit));
    ['west', 'south', 'east', 'north'].forEach((k) => {
      const v = params?.[k as keyof typeof params];
      if (v != null) q.set(k, String(v));
    });
    return request<{ items: QueueItem[] }>(`/queue?${q}`);
  },
  logDisposition: (id: string, body: { disposition: string; notes?: string; callback_days?: number; callback_date?: string }) =>
    request(`/queue/${id}/log`, { method: 'POST', body: JSON.stringify(body) }),
  undoDisposition: (id: string) => request(`/queue/${id}/undo`, { method: 'POST' }),
  leads: (params: Record<string, string | number | boolean | undefined>) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') q.set(k, String(v)); });
    return request<{ items: LeadRow[]; total: number; page: number; pages: number }>(`/leads?${q}`);
  },
  lead: (id: string) => request<LeadDetail>(`/leads/${id}`),
  patchStatus: (id: string, status: string) =>
    request(`/leads/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  addNote: (id: string, body: string) =>
    request(`/leads/${id}/notes`, { method: 'POST', body: JSON.stringify({ body }) }),
  patchDeal: (id: string, body: Record<string, unknown>) =>
    request(`/leads/${id}/deal`, { method: 'PATCH', body: JSON.stringify(body) }),
  mapPoints: (bbox: { west: number; south: number; east: number; north: number }) => {
    const q = new URLSearchParams(bbox as unknown as Record<string, string>);
    return request<{ type: string; features: GeoFeature[] }>(`/map/points?${q}`);
  },
  search: (q: string) => request<{ items: SearchHit[] }>(`/search?q=${encodeURIComponent(q)}`),
  campaigns: () => request<{ items: CampaignSummary[] }>('/campaigns'),
  campaign: (id: string) => request<{ batch_id: string; items: CampaignRow[]; total: number }>(`/campaigns/${id}`),
  pipeline: () => request<Record<string, PipelineCard[]>>('/pipeline'),
  enrichProgress: () => request<EnrichProgress>('/enrich/progress'),
  startEnrich: (kind: 'enrich' | 'verify', limit?: number) =>
    request('/enrich/start', { method: 'POST', body: JSON.stringify({ kind, limit }) }),
  analyticsIcp: () => request<{ items: DecileRow[] }>('/analytics/icp-deciles'),
  analyticsHour: () => request<{ items: HourRow[] }>('/analytics/connect-by-hour'),
  analyticsSegment: () => request<{ items: SegmentRow[] }>('/analytics/segment-funnel'),
  views: () => request<{ items: SavedView[] }>('/views'),
  createView: (name: string, filters: Record<string, unknown>) =>
    request('/views', { method: 'POST', body: JSON.stringify({ name, filters }) }),
};

export interface QueueItem {
  business_id: string;
  name: string;
  phone?: string;
  email?: string;
  category?: string;
  county?: string;
  city?: string;
  website?: string;
  icp_score: number;
  segment: string;
  status: string;
  last_notes?: string;
  last_disposition?: string;
  callback_due?: string;
}

export interface LeadRow {
  business_id: string;
  name: string;
  category?: string;
  county?: string;
  city?: string;
  icp_score?: number;
  status?: string;
  segment?: string;
  phone?: string;
  email?: string;
}

export interface LeadDetail {
  business: Record<string, unknown>;
  contacts: Record<string, unknown>[];
  touches: Record<string, unknown>[];
  notes: Record<string, unknown>[];
  status_history: Record<string, unknown>[];
  deal?: Record<string, unknown>;
}

export interface GeoFeature {
  type: string;
  geometry: { type: string; coordinates: number[] };
  properties: Record<string, unknown>;
}

export interface SearchHit {
  business_id: string;
  name: string;
  category?: string;
  county?: string;
  icp_score?: number;
}

export interface CampaignSummary {
  batch_id: string;
  total: number;
  sendable: number;
}

export interface CampaignRow {
  business_id: string;
  name: string;
  email?: string;
  verify_status?: string;
  icp_score: number;
  status: string;
  next_email?: string;
  next_call?: string;
}

export interface PipelineCard {
  business_id: string;
  name: string;
  icp_score: number;
  segment: string;
  last_touch?: string;
}

export interface EnrichProgress {
  emails_found: number;
  emails_verified: number;
  emails_total_contacts: number;
  websites_discovered: number;
  businesses_total: number;
  verification_pct: number;
  latest_job?: Record<string, unknown>;
}

export interface DecileRow { decile_bucket: number; total: number; wins: number; win_rate: number }
export interface HourRow { hour: number; total: number; connected: number }
export interface SegmentRow { segment: string; total: number; working: number; meeting: number; won: number }
export interface SavedView { id: number; name: string; filters: Record<string, unknown> }

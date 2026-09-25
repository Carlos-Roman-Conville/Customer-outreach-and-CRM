const BASE = '/api';

type QueryValue = string | number | boolean | string[] | undefined;

function appendQueryParams(q: URLSearchParams, params: Record<string, QueryValue>) {
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === '') return;
    if (Array.isArray(v)) {
      v.forEach((item) => { if (item) q.append(k, item); });
    } else {
      q.set(k, String(v));
    }
  });
}

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
  queue: (params?: {
    limit?: number;
    west?: number;
    south?: number;
    east?: number;
    north?: number;
    category?: string[];
    county?: string;
  }) => {
    const q = new URLSearchParams();
    appendQueryParams(q, {
      limit: params?.limit,
      west: params?.west,
      south: params?.south,
      east: params?.east,
      north: params?.north,
      category: params?.category,
      county: params?.county,
    });
    const suffix = q.toString() ? `?${q}` : '';
    return request<{ items: QueueItem[] }>(`/queue${suffix}`);
  },
  logDisposition: (id: string, body: {
    disposition: string;
    notes?: string;
    callback_days?: number;
    callback_date?: string;
    discovery?: Record<string, unknown>;
  }) =>
    request(`/queue/${id}/log`, { method: 'POST', body: JSON.stringify(body) }),
  undoDisposition: (id: string) => request(`/queue/${id}/undo`, { method: 'POST' }),
  leads: (params: Record<string, QueryValue>) => {
    const q = new URLSearchParams();
    appendQueryParams(q, params);
    return request<{ items: LeadRow[]; total: number; page: number; pages: number }>(`/leads?${q}`);
  },
  lead: (id: string) => request<LeadDetail>(`/leads/${id}`),
  patchStatus: (id: string, status: string) =>
    request(`/leads/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  addNote: (id: string, body: string) =>
    request(`/leads/${id}/notes`, { method: 'POST', body: JSON.stringify({ body }) }),
  patchDeal: (id: string, body: Record<string, unknown>) =>
    request(`/leads/${id}/deal`, { method: 'PATCH', body: JSON.stringify(body) }),
  patchDiscovery: (id: string, body: Record<string, unknown>) =>
    request(`/leads/${id}/discovery`, { method: 'PATCH', body: JSON.stringify(body) }),
  mapCounties: (params?: {
    min_score?: number;
    status?: string;
    category?: string[];
  }) => {
    const q = new URLSearchParams();
    appendQueryParams(q, {
      min_score: params?.min_score,
      status: params?.status,
      category: params?.category,
    });
    const suffix = q.toString() ? `?${q}` : '';
    return request<{ items: CountyStat[] }>(`/map/counties${suffix}`);
  },
  mapPoints: (params: {
    west: number;
    south: number;
    east: number;
    north: number;
    limit?: number;
    min_score?: number;
    county?: string;
    status?: string;
    category?: string[];
    batch_id?: string;
    mode?: 'hunt' | 'cadence' | 'campaign' | 'overview';
    overdue_only?: boolean;
  }) => {
    const q = new URLSearchParams();
    appendQueryParams(q, {
      west: params.west,
      south: params.south,
      east: params.east,
      north: params.north,
      limit: params.limit,
      min_score: params.min_score,
      county: params.county,
      status: params.status,
      category: params.category,
      batch_id: params.batch_id,
      mode: params.mode,
      overdue_only: params.overdue_only,
    });
    return request<{ type: string; features: GeoFeature[] }>(`/map/points?${q}`);
  },
  search: (q: string) => request<{ items: SearchHit[] }>(`/search?q=${encodeURIComponent(q)}`),
  campaigns: () => request<{ items: CampaignSummary[] }>('/campaigns'),
  campaign: (id: string) => request<{ batch_id: string; items: CampaignRow[]; total: number }>(`/campaigns/${id}`),
  pipeline: (newLimit?: number) => {
    const q = new URLSearchParams();
    if (newLimit != null) q.set('new_limit', String(newLimit));
    const suffix = q.toString() ? `?${q}` : '';
    return request<PipelineBoard>(`/pipeline${suffix}`);
  },
  enrichProgress: () => request<EnrichProgress>('/enrich/progress'),
  startEnrich: (kind: 'enrich' | 'verify' | 'signals', limit?: number) =>
    request('/enrich/start', { method: 'POST', body: JSON.stringify({ kind, limit }) }),
  analyticsIcp: () => request<{ items: DecileRow[] }>('/analytics/icp-deciles'),
  analyticsHour: () => request<{ items: HourRow[] }>('/analytics/connect-by-hour'),
  analyticsSegment: () => request<{ items: SegmentRow[] }>('/analytics/segment-funnel'),
  analyticsDiscovery: () => request<DiscoveryAnalytics>('/analytics/discovery'),
  views: () => request<{ items: SavedView[] }>('/views'),
  createView: (name: string, filters: Record<string, unknown>) =>
    request('/views', { method: 'POST', body: JSON.stringify({ name, filters }) }),
  metaCategories: (params?: { q?: string; limit?: number; callable_only?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.q) q.set('q', params.q);
    if (params?.limit != null) q.set('limit', String(params.limit));
    if (params?.callable_only != null) q.set('callable_only', String(params.callable_only));
    const suffix = q.toString() ? `?${q}` : '';
    return request<{ items: CategoryMeta[] }>(`/meta/categories${suffix}`);
  },
  metaConfig: () =>
    request<{ call_queue_min_score: number; score_version: number; max_score: number }>(
      '/meta/config',
    ),
  categoryCount: (categories: string[]) => {
    const q = new URLSearchParams();
    categories.forEach((c) => q.append('category', c));
    return request<{ total: number; with_email: number }>(`/meta/categories/count?${q}`);
  },
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
  revenue_tier?: string;
  category_path?: string;
  status: string;
  last_notes?: string;
  last_disposition?: string;
  callback_due?: string;
  booking_platform?: string | null;
  site_scanned_at?: string | null;
  rating?: number | null;
  review_count?: number | null;
  discovery?: DiscoveryRecord | null;
}

export interface DiscoveryRecord {
  after_hours?: string | null;
  current_tool?: string | null;
  hiring_front_desk?: number | null;
  missed_calls?: string | null;
  answering_spend?: number | null;
}

export interface BusinessSignal {
  kind: string;
  value: string;
  detail?: string | null;
  source?: string;
  detected_at?: string;
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
  revenue_tier?: string;
  category_path?: string;
  phone?: string;
  email?: string;
  booking_platform?: string | null;
  site_scanned_at?: string | null;
}

export interface LeadDetail {
  business: Record<string, unknown>;
  contacts: Record<string, unknown>[];
  touches: Record<string, unknown>[];
  notes: Record<string, unknown>[];
  status_history: Record<string, unknown>[];
  deal?: Record<string, unknown>;
  signals?: BusinessSignal[];
  discovery?: DiscoveryRecord | null;
}

export interface GeoFeature {
  type: string;
  geometry: { type: string; coordinates: number[] };
  properties: Record<string, unknown>;
}

export interface CountyStat {
  county: string;
  lead_count: number;
  avg_icp: number;
  untouched_count: number;
  untouched_pct: number;
  overdue_count: number;
  in_campaign_count: number;
  opportunity: number;
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
  revenue_tier?: string;
  deal_value?: number;
  last_completed_at?: string | null;
  next_scheduled?: string | null;
  has_phone?: boolean;
  has_email?: boolean;
  is_stale?: boolean;
}

export interface PipelineColumn {
  total: number;
  deal_value: number;
  items: PipelineCard[];
}

export interface PipelineBoard {
  columns: Record<string, PipelineColumn>;
}

export interface EnrichProgress {
  emails_found: number;
  emails_verified: number;
  emails_total_contacts: number;
  websites_discovered: number;
  businesses_total: number;
  verification_pct: number;
  sites_total?: number;
  sites_scanned?: number;
  booking_detected?: number;
  latest_job?: Record<string, unknown>;
}

export interface DecileRow { decile_bucket: number; total: number; wins: number; win_rate: number }
export interface HourRow { hour: number; total: number; connected: number }
export interface SegmentRow { segment: string; total: number; working: number; meeting: number; won: number }
export interface SavedView { id: number; name: string; filters: Record<string, unknown> }
export interface CategoryMeta { category: string; total: number; with_email: number }

export interface DiscoveryAnalytics {
  discovery_total: number;
  after_hours: { key: string; count: number }[];
  missed_calls: { key: string; count: number }[];
  hiring_front_desk: { key: number; count: number }[];
  avg_answering_spend: number | null;
  booking_platforms: { key: string; count: number }[];
}

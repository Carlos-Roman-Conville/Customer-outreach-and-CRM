const SEGMENT_LABELS: Record<string, string> = {
  tier1_high_value: 'High value',
  tier2_mid_value: 'Mid value',
  tier3_low_value: 'Low value',
  unclassified: 'Unclassified',
  excluded: 'Excluded',
  // legacy segments (pre-rescore)
  tier1_home_personal_auto: 'Home & Auto Services',
  tier2_health_professional: 'Health & Professional',
  tier3_fitness_food: 'Fitness & Food',
  other: 'Other',
};

const REVENUE_TIER_LABELS: Record<string, string> = {
  A: 'Tier A',
  B: 'Tier B',
  C: 'Tier C',
  U: 'Unclassified',
  X: 'Excluded',
};

export const SCORE_TOOLTIP = 'ICP Fit Score — reachability and data quality within a revenue tier';

export function formatRevenueTier(tier: string | undefined | null): string {
  if (!tier) return '—';
  return REVENUE_TIER_LABELS[tier] || tier;
}

export function formatSegment(segment: string | undefined | null): string {
  if (!segment) return '—';
  return SEGMENT_LABELS[segment] || segment.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatCategory(category: string | undefined | null): string {
  if (!category) return '—';
  return category
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatStatus(status: string | undefined | null): string {
  if (!status) return '—';
  const map: Record<string, string> = {
    new: 'New',
    working: 'Working',
    meeting: 'Meeting',
    won: 'Won',
    dead: 'Dead',
  };
  return map[status] || status.charAt(0).toUpperCase() + status.slice(1);
}

export function formatScore(score: number | undefined | null): string {
  if (score == null || Number.isNaN(score)) return '—';
  return score.toFixed(1);
}

export function formatDate(iso: string | undefined | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function formatRelativeDate(iso: string | undefined | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfDate = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.round((startOfToday.getTime() - startOfDate.getTime()) / 86400000);
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return '1d ago';
  if (diffDays > 1) return `${diffDays}d ago`;
  if (diffDays === -1) return 'Tomorrow';
  return formatDate(iso);
}

export function formatCurrency(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '$0';
  return `$${Math.round(value).toLocaleString()}`;
}

const BOOKING_LABELS: Record<string, string> = {
  housecall_pro: 'Housecall Pro',
  servicetitan: 'ServiceTitan',
  jobber: 'Jobber',
  booksy: 'Booksy',
  vagaro: 'Vagaro',
  square_appointments: 'Square Appointments',
  acuity: 'Acuity',
  calendly: 'Calendly',
  mindbody: 'Mindbody',
  schedulicity: 'Schedulicity',
  setmore: 'Setmore',
  fresha: 'Fresha',
  styleseat: 'StyleSeat',
  zocdoc: 'Zocdoc',
  nexhealth: 'NexHealth',
  janeapp: 'Jane App',
  opentable: 'OpenTable',
  resy: 'Resy',
  toast: 'Toast',
  online_booking_link: 'Online booking link',
  podium: 'Podium',
  tawk: 'Tawk.to',
  intercom: 'Intercom',
  drift: 'Drift',
  tidio: 'Tidio',
};

export function formatBookingPlatform(platform: string | undefined | null): string {
  if (!platform) return '—';
  return BOOKING_LABELS[platform] || platform.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function bookingSignalLine(
  bookingPlatform: string | undefined | null,
  siteScannedAt: string | undefined | null,
): string {
  if (bookingPlatform) return `Uses ${formatBookingPlatform(bookingPlatform)}`;
  if (siteScannedAt) return 'No booking widget found (scanned)';
  return 'Not scanned yet';
}

export function formatRating(
  rating: number | undefined | null,
  reviewCount: number | undefined | null,
): string {
  if (rating == null || Number.isNaN(rating)) return 'No rating yet';
  const reviews = reviewCount != null && !Number.isNaN(reviewCount)
    ? `${reviewCount.toLocaleString()} review${reviewCount === 1 ? '' : 's'}`
    : 'reviews unknown';
  return `${rating.toFixed(1)} ★ · ${reviews}`;
}

export const DISCOVERY_AFTER_HOURS_LABELS: Record<string, string> = {
  owner_cell: 'Owner cell',
  answering_service: 'Answering service',
  voicemail: 'Voicemail',
  nobody: 'Nobody',
  unknown: 'Unknown',
};

export const DISCOVERY_MISSED_CALLS_LABELS: Record<string, string> = {
  none: 'None',
  some: 'Some',
  many: 'Many',
  unknown: 'Unknown',
};

export interface DiscoverySummaryInput {
  after_hours?: string | null;
  current_tool?: string | null;
  hiring_front_desk?: number | null;
  missed_calls?: string | null;
  answering_spend?: number | null;
}

export function formatDiscoverySummary(discovery: DiscoverySummaryInput | null | undefined): string {
  if (!discovery) return '';
  const parts: string[] = [];
  if (discovery.after_hours) {
    parts.push(`After hrs: ${DISCOVERY_AFTER_HOURS_LABELS[discovery.after_hours] || discovery.after_hours}`);
  }
  if (discovery.missed_calls) {
    parts.push(`Missed calls: ${DISCOVERY_MISSED_CALLS_LABELS[discovery.missed_calls] || discovery.missed_calls}`);
  }
  if (discovery.current_tool?.trim()) {
    parts.push(`Tool: ${discovery.current_tool.trim()}`);
  } else if (discovery.after_hours || discovery.missed_calls) {
    parts.push('No current tool');
  }
  if (discovery.hiring_front_desk != null) {
    parts.push(`Hiring front desk: ${discovery.hiring_front_desk ? 'Yes' : 'No'}`);
  }
  if (discovery.answering_spend != null && !Number.isNaN(discovery.answering_spend)) {
    parts.push(`Answering spend: ${formatCurrency(discovery.answering_spend)}/mo`);
  }
  return parts.join(' · ');
}

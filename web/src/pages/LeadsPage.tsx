import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { CategoryPicker } from '../components/CategoryPicker';
import { LeadDrawer } from '../components/LeadDrawer';
import {
  formatBookingPlatform,
  formatCategory,
  formatRevenueTier,
  formatScore,
  formatSegment,
  formatStatus,
  SCORE_TOOLTIP,
} from '../lib/format';

export function LeadsPage() {
  const [searchParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [county, setCounty] = useState('');
  const [segment, setSegment] = useState('');
  const [status, setStatus] = useState('');
  const [categories, setCategories] = useState<string[]>([]);
  const [hasPhone, setHasPhone] = useState(false);
  const [booking, setBooking] = useState('');
  const [minScore, setMinScore] = useState<number | undefined>(40);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    setQ(searchParams.get('q') || '');
    setCounty(searchParams.get('county') || '');
    setSegment(searchParams.get('segment') || '');
    setStatus(searchParams.get('status') || '');
    setCategories(searchParams.getAll('category').filter(Boolean));
    setHasPhone(searchParams.get('has_phone') === '1' || searchParams.get('has_phone') === 'true');
    setBooking(searchParams.get('booking') || '');
    const ms = searchParams.get('min_score');
    setMinScore(ms ? Number(ms) : 40);
    const highlight = searchParams.get('highlight');
    if (highlight) setSelected(highlight);
    setPage(1);
  }, [searchParams]);

  const { data, isLoading } = useQuery({
    queryKey: ['leads', page, q, county, segment, status, categories, hasPhone, booking, minScore],
    queryFn: () => api.leads({
      page,
      page_size: 50,
      q: q || undefined,
      county: county || undefined,
      segment: segment || undefined,
      status: status || undefined,
      category: categories.length > 0 ? categories : undefined,
      has_phone: hasPhone || undefined,
      booking: booking || undefined,
      min_score: minScore,
    }),
  });

  return (
    <div>
      <h1>Lead Database</h1>
      <div className="filters-row">
        <input placeholder="Search…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <CategoryPicker
          value={categories}
          onChange={(next) => { setCategories(next); setPage(1); }}
          callableOnly={false}
        />
        <select value={county} onChange={(e) => { setCounty(e.target.value); setPage(1); }}>
          <option value="">All counties</option>
          {['Philadelphia', 'Montgomery', 'Bucks', 'Chester', 'Delaware', 'Camden', 'Burlington', 'Gloucester'].map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select value={segment} onChange={(e) => { setSegment(e.target.value); setPage(1); }}>
          <option value="">All segments</option>
          <option value="tier1_high_value">{formatSegment('tier1_high_value')}</option>
          <option value="tier2_mid_value">{formatSegment('tier2_mid_value')}</option>
          <option value="tier3_low_value">{formatSegment('tier3_low_value')}</option>
          <option value="unclassified">{formatSegment('unclassified')}</option>
        </select>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All statuses</option>
          {['new', 'working', 'meeting', 'won', 'dead'].map((s) => (
            <option key={s} value={s}>{formatStatus(s)}</option>
          ))}
        </select>
        <select value={booking} onChange={(e) => { setBooking(e.target.value); setPage(1); }}>
          <option value="">Any booking</option>
          <option value="yes">Has booking</option>
          <option value="no">No booking (scanned)</option>
          <option value="unknown">Not scanned</option>
        </select>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <input
            type="checkbox"
            checked={hasPhone}
            onChange={(e) => { setHasPhone(e.target.checked); setPage(1); }}
          />
          Has phone
        </label>
      </div>

      <p style={{ color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
        {data ? `${data.total.toLocaleString()} matches` : '…'}
      </p>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>County</th>
              <th>Category</th>
              <th>Tier</th>
              <th>Fit</th>
              <th>Status</th>
              <th>Booking</th>
              <th>Phone</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <tr><td colSpan={8}>Loading…</td></tr>}
            {data?.items.map((row) => (
              <tr key={row.business_id} style={{ cursor: 'pointer' }} onClick={() => setSelected(row.business_id)}>
                <td>{row.name}</td>
                <td>{row.county}</td>
                <td>{formatCategory(row.category)}</td>
                <td>{formatRevenueTier(row.revenue_tier)}</td>
                <td title={SCORE_TOOLTIP}>{formatScore(row.icp_score)}</td>
                <td>{formatStatus(row.status)}</td>
                <td>
                  {row.booking_platform
                    ? formatBookingPlatform(row.booking_platform)
                    : row.site_scanned_at
                      ? 'None'
                      : '—'}
                </td>
                <td>{row.phone}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
        <button className="btn btn-ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
        <span>Page {page} / {data?.pages || 1}</span>
        <button className="btn btn-ghost" disabled={page >= (data?.pages || 1)} onClick={() => setPage((p) => p + 1)}>Next</button>
      </div>

      <LeadDrawer id={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { LeadDrawer } from '../components/LeadDrawer';

export function LeadsPage() {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [county, setCounty] = useState('');
  const [segment, setSegment] = useState('');
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['leads', page, q, county, segment, status],
    queryFn: () => api.leads({
      page, page_size: 50,
      q: q || undefined,
      county: county || undefined,
      segment: segment || undefined,
      status: status || undefined,
      min_score: 25,
    }),
  });

  return (
    <div>
      <h1>Lead Database</h1>
      <div className="filters-row">
        <input placeholder="Search…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select value={county} onChange={(e) => { setCounty(e.target.value); setPage(1); }}>
          <option value="">All counties</option>
          {['Philadelphia', 'Montgomery', 'Bucks', 'Chester', 'Delaware', 'Camden', 'Burlington', 'Gloucester'].map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select value={segment} onChange={(e) => { setSegment(e.target.value); setPage(1); }}>
          <option value="">All segments</option>
          <option value="tier1_home_personal_auto">Tier 1</option>
          <option value="tier2_health_professional">Tier 2</option>
          <option value="tier3_fitness_food">Tier 3</option>
        </select>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All statuses</option>
          {['new', 'working', 'meeting', 'won', 'dead'].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
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
              <th>Score</th>
              <th>Status</th>
              <th>Phone</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <tr><td colSpan={6}>Loading…</td></tr>}
            {data?.items.map((row) => (
              <tr key={row.business_id} style={{ cursor: 'pointer' }} onClick={() => setSelected(row.business_id)}>
                <td>{row.name}</td>
                <td>{row.county}</td>
                <td>{row.category}</td>
                <td>{row.icp_score?.toFixed(1)}</td>
                <td>{row.status}</td>
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

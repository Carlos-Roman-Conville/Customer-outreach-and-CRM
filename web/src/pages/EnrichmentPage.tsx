import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';

export function EnrichmentPage() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ['enrich'], queryFn: api.enrichProgress, refetchInterval: 5000 });

  const startMut = useMutation({
    mutationFn: (kind: 'enrich' | 'verify' | 'signals') => api.startEnrich(kind),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['enrich'] }),
  });

  const job = data?.latest_job as Record<string, unknown> | undefined;
  const scanPct = data?.sites_total
    ? Math.min(100, ((data.sites_scanned || 0) / data.sites_total) * 100)
    : 0;

  return (
    <div>
      <h1>Enrichment Status</h1>
      <p style={{ color: 'var(--text-muted)' }}>Email discovery, verification, and website booking signals</p>

      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="label">Businesses with email</div>
          <div className="value">{data?.emails_found?.toLocaleString()}</div>
          <div className="progress-bar"><span style={{ width: `${Math.min(100, (data?.emails_found || 0) / (data?.businesses_total || 1) * 100)}%` }} /></div>
        </div>
        <div className="kpi-card">
          <div className="label">Emails verified</div>
          <div className="value">{data?.emails_verified?.toLocaleString()}</div>
          <div className="progress-bar"><span style={{ width: `${data?.verification_pct || 0}%` }} /></div>
        </div>
        <div className="kpi-card">
          <div className="label">Websites discovered</div>
          <div className="value">{data?.websites_discovered?.toLocaleString()}</div>
        </div>
        <div className="kpi-card">
          <div className="label">Sites scanned</div>
          <div className="value">{data?.sites_scanned?.toLocaleString() ?? '0'}</div>
          <div className="progress-bar"><span style={{ width: `${scanPct}%` }} /></div>
        </div>
        <div className="kpi-card">
          <div className="label">Booking detected</div>
          <div className="value">{data?.booking_detected?.toLocaleString() ?? '0'}</div>
        </div>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <h3>Background jobs</h3>
        {job && (
          <p>Latest: {String(job.kind)} · {String(job.status)} · {String(job.message || '').slice(0, 120)}</p>
        )}
        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem', flexWrap: 'wrap' }}>
          <button className="btn btn-primary" onClick={() => startMut.mutate('verify')} disabled={startMut.isPending}>
            Start full verification
          </button>
          <button className="btn btn-ghost" onClick={() => startMut.mutate('enrich')} disabled={startMut.isPending}>
            Start email enrichment
          </button>
          <button className="btn btn-ghost" onClick={() => startMut.mutate('signals')} disabled={startMut.isPending}>
            Scan websites for booking software
          </button>
        </div>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '1rem' }}>
          Verification must reach 100% before email batch export is allowed. Booking scans only crawl businesses with a website.
        </p>
      </div>
    </div>
  );
}

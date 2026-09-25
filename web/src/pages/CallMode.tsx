import { useCallback, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { QueueItem } from '../api/client';
import { CategoryPicker } from '../components/CategoryPicker';
import { DiscoveryPanel, discoveryForSubmit, emptyDiscovery, hasDiscoveryValues, type DiscoveryValues } from '../components/DiscoveryPanel';
import { bookingSignalLine, formatCategory, formatDiscoverySummary, formatRating, formatRevenueTier, formatScore, formatSegment, SCORE_TOOLTIP } from '../lib/format';
import { useCallStore } from '../store/callStore';

const DISPOSITIONS = [
  { key: 'connected', label: '1 Connected', disposition: 'connected' },
  { key: 'no_answer', label: '2 No Answer', disposition: 'no_answer' },
  { key: 'callback', label: '3 Callback', disposition: 'callback' },
  { key: 'not_interested', label: '4 Not Interested', disposition: 'not_interested' },
  { key: 'dead', label: '5 Dead', disposition: 'dead' },
];

function CallEmptyState({
  bbox,
  county,
  categories,
  onClearFilters,
  onLoadTop,
  contactableCount,
  minScore,
}: {
  bbox: ReturnType<typeof useCallStore.getState>['bbox'];
  county: string | null;
  categories: string[];
  onClearFilters: () => void;
  onLoadTop: () => void;
  contactableCount: number;
  minScore: number;
}) {
  const hasFilters = Boolean(bbox || county || categories.length > 0);

  return (
    <div className="call-mode call-empty">
      <div className="call-empty-panel">
        <h1>No calls in queue</h1>
        <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
          The queue is empty with your current filters. Adjust filters or load top contactable leads to start dialing.
        </p>

        <div className="call-empty-filters card" style={{ textAlign: 'left', marginBottom: '1.5rem' }}>
          <h3 style={{ marginTop: 0 }}>Active filters</h3>
          <ul style={{ margin: 0, paddingLeft: '1.25rem', lineHeight: 1.8 }}>
            <li>Min ICP score: {minScore}+</li>
            <li>Must have phone number</li>
            <li>Status: not Won or Dead</li>
            <li>County: {county || 'All'}</li>
            <li>Territory map bbox: {bbox ? 'On (from map view)' : 'Off'}</li>
            <li>
              Categories:{' '}
              {categories.length === 0
                ? 'All'
                : categories.map((c) => formatCategory(c)).join(', ')}
            </li>
          </ul>
          {bbox && (
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 0 }}>
              Bbox: {bbox.west.toFixed(2)}, {bbox.south.toFixed(2)} → {bbox.east.toFixed(2)}, {bbox.north.toFixed(2)}
            </p>
          )}
        </div>

        <p style={{ marginBottom: '1rem' }}>
          <strong>{contactableCount.toLocaleString()}</strong> leads have phones and meet the score threshold.
        </p>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'center' }}>
          {hasFilters && (
            <button type="button" className="btn btn-ghost" onClick={onClearFilters}>
              Clear filters
            </button>
          )}
          <button type="button" className="btn btn-primary" onClick={onLoadTop}>
            Load top contactable leads
          </button>
        </div>
      </div>
    </div>
  );
}

export function CallMode() {
  const qc = useQueryClient();
  const bbox = useCallStore((s) => s.bbox);
  const setBbox = useCallStore((s) => s.setBbox);
  const county = useCallStore((s) => s.county);
  const setCounty = useCallStore((s) => s.setCounty);
  const categories = useCallStore((s) => s.categories);
  const setCategories = useCallStore((s) => s.setCategories);
  const index = useCallStore((s) => s.index);
  const setIndex = useCallStore((s) => s.setIndex);
  const [notes, setNotes] = useState('');
  const [discoveryOpen, setDiscoveryOpen] = useState(false);
  const [discovery, setDiscovery] = useState<DiscoveryValues>(emptyDiscovery());

  const { data: stats } = useQuery({ queryKey: ['stats'], queryFn: api.stats });
  const { data: appConfig } = useQuery({ queryKey: ['metaConfig'], queryFn: api.metaConfig });
  const minScore = appConfig?.call_queue_min_score ?? 44;
  const { data, refetch } = useQuery({
    queryKey: ['queue', bbox, county, categories],
    queryFn: () => api.queue({
      limit: 40,
      ...(bbox || {}),
      county: county || undefined,
      category: categories.length > 0 ? categories : undefined,
    }),
  });

  const items = data?.items || [];
  const current: QueueItem | undefined = items[index];

  useEffect(() => {
    if (!current) return;
    setDiscovery({
      after_hours: current.discovery?.after_hours || undefined,
      current_tool: current.discovery?.current_tool || undefined,
      hiring_front_desk: current.discovery?.hiring_front_desk ?? null,
      missed_calls: current.discovery?.missed_calls || undefined,
      answering_spend: current.discovery?.answering_spend ?? null,
    });
    setDiscoveryOpen(Boolean(current.discovery));
  }, [current?.business_id]);

  const logMut = useMutation({
    mutationFn: ({ disposition, callback_date }: { disposition: string; callback_date?: string }) =>
      api.logDisposition(current!.business_id, {
        disposition,
        notes,
        callback_date,
        discovery: discoveryForSubmit(discovery) as Record<string, unknown> | undefined,
      }),
    onSuccess: () => {
      setNotes('');
      setDiscovery(emptyDiscovery());
      setDiscoveryOpen(false);
      setIndex((i) => i + 1);
      refetch();
      qc.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  const undoMut = useMutation({
    mutationFn: () => api.undoDisposition(current!.business_id),
    onSuccess: () => refetch(),
  });

  const handleDisposition = useCallback((disposition: string) => {
    if (!current) return;
    if (disposition === 'callback') {
      const d = prompt('Callback date (YYYY-MM-DD):', new Date(Date.now() + 2 * 864e5).toISOString().slice(0, 10));
      if (!d) return;
      logMut.mutate({ disposition, callback_date: d });
      return;
    }
    logMut.mutate({ disposition });
  }, [current, logMut]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const map: Record<string, string> = { '1': 'connected', '2': 'no_answer', '3': 'callback', '4': 'not_interested', '5': 'dead' };
      if (map[e.key]) handleDisposition(map[e.key]);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handleDisposition]);

  const handleClearFilters = () => {
    setBbox(null);
    setCounty(null);
    setCategories([]);
    setIndex(0);
    refetch();
  };

  const handleLoadTop = () => {
    setBbox(null);
    setCounty(null);
    setCategories([]);
    setIndex(0);
    refetch();
  };

  const picker = (
    <div style={{ marginBottom: '1rem' }}>
      <CategoryPicker value={categories} onChange={setCategories} />
    </div>
  );

  if (!current) {
    return (
      <>
        {picker}
        <CallEmptyState
          bbox={bbox}
          county={county}
          categories={categories}
          onClearFilters={handleClearFilters}
          onLoadTop={handleLoadTop}
          contactableCount={Number(stats?.contactable_leads || 0)}
          minScore={minScore}
        />
      </>
    );
  }

  return (
    <>
      {picker}
      <div className="call-mode">
        <div className="call-main">
          <p style={{ opacity: 0.6, fontSize: '0.85rem' }}>Call {index + 1} of {items.length}</p>
          <h1>{current.name}</h1>
          <a className="call-phone" href={`tel:${current.phone}`}>{current.phone}</a>
          <div className="call-meta">
            <div>{formatCategory(current.category)} · {current.city}, {current.county}</div>
            <div>
              <span title={SCORE_TOOLTIP}>Fit {formatScore(current.icp_score)}</span>
              {' · '}
              {formatRevenueTier(current.revenue_tier)}
              {' · '}
              {formatSegment(current.segment)}
            </div>
            {current.website && <div><a href={current.website} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-soft)' }}>{current.website}</a></div>}
            {current.email && <div>{current.email}</div>}
            <div style={{ marginTop: '0.5rem', opacity: 0.85 }}>
              {bookingSignalLine(current.booking_platform, current.site_scanned_at)}
            </div>
            <div style={{ marginTop: '0.35rem', opacity: 0.85 }}>
              {formatRating(current.rating, current.review_count)}
            </div>
            {hasDiscoveryValues(current.discovery) && (
              <div style={{ marginTop: '0.75rem', opacity: 0.9, fontSize: '0.9rem' }}>
                <span style={{ opacity: 0.7 }}>Last connected call: </span>
                {formatDiscoverySummary(current.discovery)}
              </div>
            )}
            {current.last_notes && <div style={{ marginTop: '1rem' }}>Last note: {current.last_notes}</div>}
          </div>

          <textarea
            placeholder="Call notes…"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            style={{ width: '100%', marginTop: '1.5rem', background: 'var(--ink-soft)', color: 'var(--paper)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '0.75rem' }}
          />

          <div style={{ marginTop: '1rem' }}>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ color: 'var(--paper)', marginBottom: discoveryOpen ? '0.75rem' : 0 }}
              onClick={() => setDiscoveryOpen((o) => !o)}
            >
              {discoveryOpen ? 'Hide discovery' : 'Discovery (connected calls)'}
            </button>
            {discoveryOpen && (
              <DiscoveryPanel value={discovery} onChange={setDiscovery} compact />
            )}
          </div>

          <div className="disposition-grid">
            {DISPOSITIONS.map((d) => (
              <button key={d.key} onClick={() => handleDisposition(d.disposition)} disabled={logMut.isPending}>
                {d.label}
              </button>
            ))}
          </div>

          <div style={{ marginTop: '1rem', display: 'flex', gap: '0.75rem' }}>
            <button className="btn btn-ghost" style={{ color: 'var(--paper)' }} onClick={() => undoMut.mutate()}>Undo last</button>
            <button className="btn btn-ghost" style={{ color: 'var(--paper)' }} onClick={() => setIndex(index + 1)}>Skip</button>
          </div>
        </div>

        <div className="call-sidebar">
          <h3 style={{ color: 'var(--paper)' }}>Up next</h3>
          {items.slice(index + 1, index + 11).map((item) => (
            <div key={item.business_id} className="queue-item">
              <strong>{item.name}</strong>
              <div>{item.phone}</div>
              <div style={{ opacity: 0.6 }}>
                <span title={SCORE_TOOLTIP}>Fit {formatScore(item.icp_score)}</span>
                {' · '}
                {formatRevenueTier(item.revenue_tier)}
                {' · '}
                {item.county}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

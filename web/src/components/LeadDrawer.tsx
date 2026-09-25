import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { LeadDetail } from '../api/client';
import { DiscoveryPanel, discoveryForSubmit, type DiscoveryValues } from '../components/DiscoveryPanel';
import {
  bookingSignalLine,
  formatBookingPlatform,
  formatCategory,
  formatDate,
  formatRevenueTier,
  formatScore,
  formatSegment,
  formatStatus,
  SCORE_TOOLTIP,
} from '../lib/format';

export function LeadDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['lead', id],
    queryFn: () => api.lead(id!),
    enabled: !!id,
  });

  const [discovery, setDiscovery] = useState<DiscoveryValues>({});

  useEffect(() => {
    if (!data?.discovery) {
      setDiscovery({});
      return;
    }
    const d = data.discovery;
    setDiscovery({
      after_hours: d.after_hours || undefined,
      current_tool: d.current_tool || undefined,
      hiring_front_desk: d.hiring_front_desk ?? null,
      missed_calls: d.missed_calls || undefined,
      answering_spend: d.answering_spend ?? null,
    });
  }, [data?.discovery, id]);

  const noteMut = useMutation({
    mutationFn: (body: string) => api.addNote(id!, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lead', id] }),
  });

  const dealMut = useMutation({
    mutationFn: (value: number) => api.patchDeal(id!, { value }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lead', id] }),
  });

  const discoveryMut = useMutation({
    mutationFn: () => api.patchDiscovery(id!, (discoveryForSubmit(discovery) || discovery) as Record<string, unknown>),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lead', id] }),
  });

  if (!id || !data) return null;

  const lead = data as LeadDetail;
  const biz = lead.business;

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer">
        <button className="btn btn-ghost" onClick={onClose} style={{ marginBottom: '1rem' }}>Close</button>
        <h2>{String(biz.name)}</h2>
        <p style={{ color: 'var(--text-muted)' }}>
          {formatCategory(String(biz.category || ''))} · {String(biz.county || '')} ·{' '}
          <span title={SCORE_TOOLTIP}>Fit {formatScore(Number(biz.icp_score || 0))}</span>
          {' · '}
          {formatRevenueTier(String(biz.revenue_tier || ''))}
          {' · '}
          {formatSegment(String(biz.segment || ''))}
        </p>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          {bookingSignalLine(
            biz.booking_platform as string | null | undefined,
            biz.site_scanned_at as string | null | undefined,
          )}
        </p>

        <h3>Contacts</h3>
        <ul>
          {lead.contacts.map((c) => (
            <li key={String(c.id)}>{String(c.kind)}: {String(c.value)} {c.verify_status ? `(${String(c.verify_status)})` : ''}</li>
          ))}
        </ul>

        {lead.signals && lead.signals.length > 0 && (
          <>
            <h3>Signals</h3>
            <ul>
              {lead.signals.map((s, i) => (
                <li key={`${s.kind}-${s.value}-${i}`}>
                  {s.kind}: {formatBookingPlatform(s.value)}
                  {s.detail ? ` (${s.detail})` : ''}
                </li>
              ))}
            </ul>
          </>
        )}

        <h3>Discovery</h3>
        <DiscoveryPanel value={discovery} onChange={setDiscovery} />
        <button
          type="button"
          className="btn btn-primary"
          style={{ marginTop: '0.75rem' }}
          onClick={() => discoveryMut.mutate()}
          disabled={discoveryMut.isPending}
        >
          Save discovery
        </button>

        <h3>Deal</h3>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <input
            type="number"
            defaultValue={Number(lead.deal?.value || 2500)}
            onBlur={(e) => dealMut.mutate(Number(e.target.value))}
            style={{ width: 120, padding: '0.5rem' }}
          />
          <span>Stage: {formatStatus(String(lead.deal?.stage || biz.status || 'new'))}</span>
        </div>

        <h3>Timeline</h3>
        {[...lead.touches, ...lead.notes.map((n) => ({ ...n, _type: 'note' as const }))].slice(0, 20).map((t, i) => (
          <div key={i} style={{ fontSize: '0.85rem', marginBottom: '0.5rem', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border)' }}>
            {'body' in t && t.body != null
              ? `Note · ${formatDate(String((t as Record<string, unknown>).created_at || ''))}: ${String(t.body)}`
              : `${String((t as Record<string, unknown>).channel || '')} · ${formatDate(String((t as Record<string, unknown>).completed_at || (t as Record<string, unknown>).scheduled_for || ''))} · ${formatStatus(String((t as Record<string, unknown>).disposition || ''))} · ${String((t as Record<string, unknown>).notes || '')}`}
          </div>
        ))}

        <h3>Add note</h3>
        <form onSubmit={(e) => {
          e.preventDefault();
          const fd = new FormData(e.currentTarget);
          const body = String(fd.get('body') || '');
          if (body) noteMut.mutate(body);
          e.currentTarget.reset();
        }}>
          <textarea name="body" rows={3} style={{ width: '100%', marginBottom: '0.5rem' }} />
          <button type="submit" className="btn btn-primary">Save note</button>
        </form>
      </div>
    </>
  );
}

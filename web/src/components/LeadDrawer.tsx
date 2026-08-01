import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { LeadDetail } from '../api/client';

export function LeadDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['lead', id],
    queryFn: () => api.lead(id!),
    enabled: !!id,
  });

  const noteMut = useMutation({
    mutationFn: (body: string) => api.addNote(id!, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lead', id] }),
  });

  const dealMut = useMutation({
    mutationFn: (value: number) => api.patchDeal(id!, { value }),
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
          {String(biz.category || '')} · {String(biz.county || '')} · ICP {Number(biz.icp_score || 0).toFixed(1)}
        </p>

        <h3>Contacts</h3>
        <ul>
          {lead.contacts.map((c) => (
            <li key={String(c.id)}>{String(c.kind)}: {String(c.value)} {c.verify_status ? `(${String(c.verify_status)})` : ''}</li>
          ))}
        </ul>

        <h3>Deal</h3>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <input
            type="number"
            defaultValue={Number(lead.deal?.value || 2500)}
            onBlur={(e) => dealMut.mutate(Number(e.target.value))}
            style={{ width: 120, padding: '0.5rem' }}
          />
          <span>stage: {String(lead.deal?.stage || biz.status || 'new')}</span>
        </div>

        <h3>Timeline</h3>
        {[...lead.touches, ...lead.notes.map((n) => ({ ...n, _type: 'note' as const }))].slice(0, 20).map((t, i) => (
          <div key={i} style={{ fontSize: '0.85rem', marginBottom: '0.5rem', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border)' }}>
            {'body' in t && t.body != null
              ? `Note: ${String(t.body)}`
              : `${String((t as Record<string, unknown>).channel || '')} · ${String((t as Record<string, unknown>).disposition || (t as Record<string, unknown>).scheduled_for || '')} · ${String((t as Record<string, unknown>).notes || '')}`}
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

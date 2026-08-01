import { useCallback, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { QueueItem } from '../api/client';
import { useCallStore } from '../store/callStore';

const DISPOSITIONS = [
  { key: 'connected', label: '1 Connected', disposition: 'connected' },
  { key: 'no_answer', label: '2 No Answer', disposition: 'no_answer' },
  { key: 'callback', label: '3 Callback', disposition: 'callback' },
  { key: 'not_interested', label: '4 Not Interested', disposition: 'not_interested' },
  { key: 'dead', label: '5 Dead', disposition: 'dead' },
];

export function CallMode() {
  const qc = useQueryClient();
  const bbox = useCallStore((s) => s.bbox);
  const index = useCallStore((s) => s.index);
  const setIndex = useCallStore((s) => s.setIndex);
  const [notes, setNotes] = useState('');
  const [callbackDate, setCallbackDate] = useState('');

  const { data, refetch } = useQuery({
    queryKey: ['queue', bbox],
    queryFn: () => api.queue({ limit: 40, ...bbox || {} }),
  });

  const items = data?.items || [];
  const current: QueueItem | undefined = items[index];

  const logMut = useMutation({
    mutationFn: ({ disposition, callback_date }: { disposition: string; callback_date?: string }) =>
      api.logDisposition(current!.business_id, { disposition, notes, callback_date }),
    onSuccess: () => {
      setNotes('');
      setCallbackDate('');
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
    if (disposition === 'callback' && !callbackDate) {
      const d = prompt('Callback date (YYYY-MM-DD):', new Date(Date.now() + 2 * 864e5).toISOString().slice(0, 10));
      if (!d) return;
      logMut.mutate({ disposition, callback_date: d });
      return;
    }
    logMut.mutate({ disposition });
  }, [current, callbackDate, logMut, notes]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const map: Record<string, string> = { '1': 'connected', '2': 'no_answer', '3': 'callback', '4': 'not_interested', '5': 'dead' };
      if (map[e.key]) handleDisposition(map[e.key]);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handleDisposition]);

  if (!current) return <div className="call-mode"><p>No calls in queue. Check filters or run scoring.</p></div>;

  return (
    <div className="call-mode">
      <div className="call-main">
        <p style={{ opacity: 0.6, fontSize: '0.85rem' }}>Call {index + 1} of {items.length}</p>
        <h1>{current.name}</h1>
        <a className="call-phone" href={`tel:${current.phone}`}>{current.phone}</a>
        <div className="call-meta">
          <div>{current.category} · {current.city}, {current.county}</div>
          <div>ICP {current.icp_score?.toFixed(1)} · {current.segment}</div>
          {current.website && <div><a href={current.website} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-soft)' }}>{current.website}</a></div>}
          {current.email && <div>{current.email}</div>}
          {current.last_notes && <div style={{ marginTop: '1rem' }}>Last note: {current.last_notes}</div>}
        </div>

        <textarea
          placeholder="Call notes…"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          style={{ width: '100%', marginTop: '1.5rem', background: 'var(--ink-soft)', color: 'var(--paper)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '0.75rem' }}
        />

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
            <div style={{ opacity: 0.6 }}>{item.icp_score?.toFixed(0)} · {item.county}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const { data } = useQuery({
    queryKey: ['search', q],
    queryFn: () => api.search(q),
    enabled: open && q.length >= 2,
  });

  if (!open) return null;

  return (
    <div className="palette-overlay" onClick={() => setOpen(false)}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <input
          autoFocus
          placeholder="Search businesses, phones, emails…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {(data?.items || []).map((item) => (
          <div
            key={item.business_id}
            className="palette-item"
            onClick={() => {
              navigate(`/leads?highlight=${item.business_id}`);
              setOpen(false);
            }}
          >
            <strong>{item.name}</strong>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              {item.category} · {item.county} · score {item.icp_score?.toFixed(0)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

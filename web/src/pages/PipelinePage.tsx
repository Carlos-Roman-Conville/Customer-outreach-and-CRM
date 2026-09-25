import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { PipelineCard } from '../api/client';
import { LeadDrawer } from '../components/LeadDrawer';
import {
  formatCurrency,
  formatRelativeDate,
  formatRevenueTier,
  formatScore,
  formatSegment,
  formatStatus,
  SCORE_TOOLTIP,
} from '../lib/format';

const COLUMNS = ['new', 'working', 'meeting', 'won', 'dead'] as const;
const NEW_PAGE_SIZE = 25;

function PipelineCardView({
  card,
  onOpen,
  onDragStart,
}: {
  card: PipelineCard;
  onOpen: () => void;
  onDragStart: (e: React.DragEvent) => void;
}) {
  return (
    <div
      className={`kanban-card${card.is_stale ? ' kanban-card-stale' : ''}`}
      draggable
      onDragStart={onDragStart}
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') onOpen(); }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'flex-start' }}>
        <strong>{card.name}</strong>
        {card.is_stale && <span className="stale-badge">Stale</span>}
      </div>
      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
        <span title={SCORE_TOOLTIP}>Fit {formatScore(card.icp_score)}</span>
        {' · '}
        {formatRevenueTier(card.revenue_tier)}
        {' · '}
        {formatSegment(card.segment)}
      </div>
      <div className="kanban-card-badges">
        <span className={card.has_phone ? 'contact-badge' : 'contact-badge muted'}>Phone</span>
        <span className={card.has_email ? 'contact-badge' : 'contact-badge muted'}>Email</span>
      </div>
      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
        Last: {formatRelativeDate(card.last_completed_at)}
        {card.next_scheduled && (
          <> · Next: {formatRelativeDate(card.next_scheduled)}</>
        )}
      </div>
    </div>
  );
}

export function PipelinePage() {
  const qc = useQueryClient();
  const [searchParams] = useSearchParams();
  const highlightStage = searchParams.get('stage');
  const [newLimit, setNewLimit] = useState(NEW_PAGE_SIZE);
  const [selected, setSelected] = useState<string | null>(null);
  const colRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const { data } = useQuery({
    queryKey: ['pipeline', newLimit],
    queryFn: () => api.pipeline(newLimit),
  });

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api.patchStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  });

  useEffect(() => {
    if (!highlightStage) return;
    const el = colRefs.current[highlightStage];
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  }, [highlightStage, data]);

  const onDrop = (businessId: string, status: string) => {
    statusMut.mutate({ id: businessId, status });
  };

  return (
    <div>
      <h1>Pipeline Board</h1>
      <p style={{ color: 'var(--text-muted)' }}>Drag cards between stages · click a card for details</p>
      <div className="kanban">
        {COLUMNS.map((col) => {
          const column = data?.columns?.[col];
          const items = column?.items || [];
          const total = column?.total ?? 0;
          const dealValue = column?.deal_value ?? 0;
          const header = dealValue > 0
            ? `${formatStatus(col)} (${total}) · ${formatCurrency(dealValue)}`
            : `${formatStatus(col)} (${total})`;

          return (
            <div
              key={col}
              ref={(el) => { colRefs.current[col] = el; }}
              className={`kanban-col${highlightStage === col ? ' kanban-col-highlight' : ''}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                const id = e.dataTransfer.getData('text/plain');
                if (id) onDrop(id, col);
              }}
            >
              <h3>{header}</h3>
              {items.map((card) => (
                <PipelineCardView
                  key={card.business_id}
                  card={card}
                  onOpen={() => setSelected(card.business_id)}
                  onDragStart={(e) => e.dataTransfer.setData('text/plain', card.business_id)}
                />
              ))}
              {col === 'new' && total > items.length && (
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ width: '100%', marginTop: '0.25rem' }}
                  onClick={() => setNewLimit((n) => n + NEW_PAGE_SIZE)}
                >
                  Show more ({items.length} of {total})
                </button>
              )}
            </div>
          );
        })}
      </div>
      <LeadDrawer id={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

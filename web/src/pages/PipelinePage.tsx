import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { PipelineCard } from '../api/client';

const COLUMNS = ['new', 'working', 'meeting', 'won', 'dead'] as const;

export function PipelinePage() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ['pipeline'], queryFn: api.pipeline });

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api.patchStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  });

  const onDrop = (businessId: string, status: string) => {
    statusMut.mutate({ id: businessId, status });
  };

  return (
    <div>
      <h1>Pipeline Board</h1>
      <p style={{ color: 'var(--text-muted)' }}>Drag cards between stages (top 500 scored leads)</p>
      <div className="kanban">
        {COLUMNS.map((col) => (
          <div
            key={col}
            className="kanban-col"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              const id = e.dataTransfer.getData('text/plain');
              if (id) onDrop(id, col);
            }}
          >
            <h3 style={{ textTransform: 'capitalize' }}>{col}</h3>
            {(data?.[col] || []).slice(0, 40).map((card: PipelineCard) => (
              <div
                key={card.business_id}
                className="kanban-card"
                draggable
                onDragStart={(e) => e.dataTransfer.setData('text/plain', card.business_id)}
              >
                <strong>{card.name}</strong>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {card.icp_score?.toFixed(0)} · {card.segment}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

export function CampaignsPage() {
  const [batchId, setBatchId] = useState<string | null>(null);
  const { data: list } = useQuery({ queryKey: ['campaigns'], queryFn: api.campaigns });
  const { data: detail } = useQuery({
    queryKey: ['campaign', batchId],
    queryFn: () => api.campaign(batchId!),
    enabled: !!batchId,
  });

  return (
    <div>
      <h1>Email Campaigns</h1>
      <p style={{ color: 'var(--text-muted)' }}>Weekly batches with verification status and cadence step</p>

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '1rem' }}>
        <div className="card">
          <h3>Batches</h3>
          {(list?.items || []).slice(0, 30).map((b) => (
            <button
              key={b.batch_id}
              className="btn btn-ghost"
              style={{ display: 'block', width: '100%', marginBottom: '0.5rem', textAlign: 'left' }}
              onClick={() => setBatchId(b.batch_id)}
            >
              {b.batch_id}
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                {b.total} leads · {b.sendable} sendable
              </div>
            </button>
          ))}
        </div>

        <div className="table-wrap">
          {detail ? (
            <table>
              <thead>
                <tr>
                  <th>Business</th>
                  <th>Email</th>
                  <th>Verify</th>
                  <th>Next email</th>
                  <th>Next call</th>
                </tr>
              </thead>
              <tbody>
                {detail.items.slice(0, 100).map((row) => (
                  <tr key={row.business_id}>
                    <td><Link to={`/leads?highlight=${row.business_id}`}>{row.name}</Link></td>
                    <td>{row.email || '—'}</td>
                    <td>{row.verify_status || 'unverified'}</td>
                    <td>{row.next_email || '—'}</td>
                    <td>{row.next_call || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p style={{ padding: '1rem' }}>Select a batch</p>
          )}
        </div>
      </div>
    </div>
  );
}

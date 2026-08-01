import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../api/client';

export function Dashboard() {
  const { data: stats } = useQuery({ queryKey: ['stats'], queryFn: api.stats });

  if (!stats) return <p>Loading dashboard…</p>;

  const activity = (stats.activity as { day: string; count: number }[]) || [];

  return (
    <div>
      <h1>Dashboard</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
        Philadelphia metro outreach at a glance
      </p>

      <div className="kpi-grid">
        <div className="kpi-card"><div className="label">Total leads</div><div className="value">{Number(stats.total_leads).toLocaleString()}</div></div>
        <div className="kpi-card"><div className="label">Contactable</div><div className="value">{Number(stats.contactable_leads).toLocaleString()}</div></div>
        <div className="kpi-card"><div className="label">Contacted this week</div><div className="value">{Number(stats.contacted_this_week)}</div></div>
        <div className="kpi-card"><div className="label">Meetings</div><div className="value">{Number(stats.meetings)}</div></div>
        <div className="kpi-card"><div className="label">Win rate</div><div className="value">{Number(stats.win_rate)}%</div></div>
        <div className="kpi-card"><div className="label">Pipeline value</div><div className="value">${Number(stats.pipeline_value).toLocaleString()}</div></div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1rem' }}>
        <div className="card">
          <h3>Outreach activity (30 days)</h3>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={activity}>
                <XAxis dataKey="day" tick={{ fontSize: 10 }} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#c45c26" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <h3>Email health</h3>
          <p>Verified: {Number(stats.emails_verified).toLocaleString()} / {Number(stats.emails_total).toLocaleString()}</p>
          <p>Sendable: {Number(stats.emails_sendable).toLocaleString()}</p>
          <div style={{ marginTop: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <Link to="/call" className="btn btn-primary">Start calling</Link>
            <Link to="/map" className="btn btn-ghost">Open territory map</Link>
            <Link to="/enrichment" className="btn btn-ghost">Run verification</Link>
          </div>
        </div>
      </div>
    </div>
  );
}

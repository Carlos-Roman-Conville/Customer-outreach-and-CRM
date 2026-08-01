import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { api } from '../api/client';

export function AnalyticsPage() {
  const { data: icp } = useQuery({ queryKey: ['analytics-icp'], queryFn: api.analyticsIcp });
  const { data: hour } = useQuery({ queryKey: ['analytics-hour'], queryFn: api.analyticsHour });
  const { data: seg } = useQuery({ queryKey: ['analytics-seg'], queryFn: api.analyticsSegment });

  return (
    <div>
      <h1>Analytics</h1>
      <p style={{ color: 'var(--text-muted)' }}>Does ICP scoring predict closes?</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
        <div className="card">
          <h3>ICP bucket vs win rate</h3>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={icp?.items || []}>
                <XAxis dataKey="decile_bucket" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="win_rate" fill="#c45c26" name="Win %" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <h3>Connect rate by hour</h3>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={hour?.items || []}>
                <XAxis dataKey="hour" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="connected" stroke="#2d6a4f" name="Connected" />
                <Line type="monotone" dataKey="total" stroke="#c45c26" name="Total calls" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <h3>Segment funnel</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Segment</th><th>Total</th><th>Working</th><th>Meeting</th><th>Won</th></tr>
            </thead>
            <tbody>
              {(seg?.items || []).map((row) => (
                <tr key={row.segment}>
                  <td>{row.segment}</td>
                  <td>{row.total}</td>
                  <td>{row.working}</td>
                  <td>{row.meeting}</td>
                  <td>{row.won}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

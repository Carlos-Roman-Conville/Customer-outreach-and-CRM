import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { api } from '../api/client';
import { formatBookingPlatform, formatCurrency, formatSegment } from '../lib/format';

const AFTER_HOURS_LABELS: Record<string, string> = {
  owner_cell: 'Owner cell',
  answering_service: 'Answering service',
  voicemail: 'Voicemail',
  nobody: 'Nobody',
  unknown: 'Unknown',
};

const MISSED_CALLS_LABELS: Record<string, string> = {
  none: 'None',
  some: 'Some',
  many: 'Many',
  unknown: 'Unknown',
};

export function AnalyticsPage() {
  const { data: icp } = useQuery({ queryKey: ['analytics-icp'], queryFn: api.analyticsIcp });
  const { data: hour } = useQuery({ queryKey: ['analytics-hour'], queryFn: api.analyticsHour });
  const { data: seg } = useQuery({ queryKey: ['analytics-seg'], queryFn: api.analyticsSegment });
  const { data: disc } = useQuery({ queryKey: ['analytics-discovery'], queryFn: api.analyticsDiscovery });

  const afterHoursData = (disc?.after_hours || []).map((r) => ({
    label: AFTER_HOURS_LABELS[r.key] || r.key,
    count: r.count,
  }));
  const missedCallsData = (disc?.missed_calls || []).map((r) => ({
    label: MISSED_CALLS_LABELS[r.key] || r.key,
    count: r.count,
  }));
  const hiringData = (disc?.hiring_front_desk || []).map((r) => ({
    label: r.key === 1 ? 'Yes' : 'No',
    count: r.count,
  }));
  const bookingData = (disc?.booking_platforms || []).map((r) => ({
    label: formatBookingPlatform(r.key),
    count: r.count,
  }));

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

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
        <div className="card">
          <h3>What we learn on calls</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            {disc?.discovery_total ?? 0} businesses with discovery captured
            {disc?.avg_answering_spend != null && (
              <> · avg answering spend {formatCurrency(disc.avg_answering_spend)}/mo</>
            )}
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
            <div>
              <h4 style={{ marginTop: 0 }}>After-hours</h4>
              <div style={{ height: 180 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={afterHoursData}>
                    <XAxis dataKey="label" hide />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#2d6a4f" name="Count" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div>
              <h4 style={{ marginTop: 0 }}>Missed calls</h4>
              <div style={{ height: 180 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={missedCallsData}>
                    <XAxis dataKey="label" hide />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#c45c26" name="Count" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
          {hiringData.length > 0 && (
            <p style={{ fontSize: '0.85rem', marginBottom: 0 }}>
              Hiring front desk: {hiringData.map((h) => `${h.label} ${h.count}`).join(' · ')}
            </p>
          )}
        </div>

        <div className="card">
          <h3>Incumbent booking software</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Detected from website scans (businesses with a URL)
          </p>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bookingData} layout="vertical" margin={{ left: 8, right: 8 }}>
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="label" width={120} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#5c4d7d" name="Businesses" />
              </BarChart>
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
                  <td>{formatSegment(row.segment)}</td>
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

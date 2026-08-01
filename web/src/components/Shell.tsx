import { NavLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/call', label: 'Call Mode' },
  { to: '/map', label: 'Territory Map' },
  { to: '/leads', label: 'Lead Database' },
  { to: '/campaigns', label: 'Email Campaigns' },
  { to: '/pipeline', label: 'Pipeline Board' },
  { to: '/enrichment', label: 'Enrichment' },
  { to: '/analytics', label: 'Analytics' },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: api.me });

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          Philly Outreach
          <small>Local CRM</small>
        </div>
        <nav>
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} end={l.to === '/'}>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div style={{ marginTop: 'auto', fontSize: '0.85rem', opacity: 0.8 }}>
          {me?.name}
          {me?.demo_mode && (
            <div style={{ marginTop: '0.5rem' }}>
              <span className="demo-badge">Demo Display</span>
            </div>
          )}
        </div>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}

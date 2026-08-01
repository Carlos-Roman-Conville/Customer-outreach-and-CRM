import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Shell } from './components/Shell';
import { CommandPalette } from './components/CommandPalette';
import { Dashboard } from './pages/Dashboard';
import { CallMode } from './pages/CallMode';
import { MapPage } from './pages/MapPage';
import { LeadsPage } from './pages/LeadsPage';
import { CampaignsPage } from './pages/CampaignsPage';
import { PipelinePage } from './pages/PipelinePage';
import { EnrichmentPage } from './pages/EnrichmentPage';
import { AnalyticsPage } from './pages/AnalyticsPage';

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Shell>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/call" element={<CallMode />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/leads" element={<LeadsPage />} />
            <Route path="/campaigns" element={<CampaignsPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/enrichment" element={<EnrichmentPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
          </Routes>
        </Shell>
        <CommandPalette />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

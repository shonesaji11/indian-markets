import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell, type NavItem } from '@/components/layout/AppShell';
import { ChartPage } from '@/pages/ChartPage';
import { DataPage } from '@/pages/DataPage';
import { OverviewPage } from '@/pages/OverviewPage';
import { ScansPage } from '@/pages/ScansPage';
import { SectorPage } from '@/pages/SectorPage';
import { WatchlistsPage } from '@/pages/WatchlistsPage';

const NAV: NavItem[] = [
  { to: '/', label: 'Overview', end: true },
  { to: '/chart', label: 'Chart' },
  { to: '/scans', label: 'Scans' },
  { to: '/watchlists', label: 'Watchlists' },
  { to: '/data', label: 'Data' },
];

export function App() {
  return (
    <AppShell title="Markets" nav={NAV}>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/chart" element={<ChartPage />} />
        <Route path="/scans" element={<ScansPage />} />
        <Route path="/sector" element={<SectorPage />} />
        <Route path="/watchlists" element={<WatchlistsPage />} />
        <Route path="/stats" element={<Navigate to="/scans" replace />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}

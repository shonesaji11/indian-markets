import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell, type NavItem } from '@/components/layout/AppShell';
import { AlertNotices } from '@/features/alerts/AlertNotices';
import { AlertsPage } from '@/pages/AlertsPage';
import { ChartPage } from '@/pages/ChartPage';
import { DataPage } from '@/pages/DataPage';
import { MoversPage } from '@/pages/MoversPage';
import { OverviewPage } from '@/pages/OverviewPage';
import { ScansPage } from '@/pages/ScansPage';
import { SectorPage } from '@/pages/SectorPage';
import { WatchlistsPage } from '@/pages/WatchlistsPage';

const NAV: NavItem[] = [
  { to: '/', label: 'Overview', end: true },
  { to: '/chart', label: 'Chart' },
  { to: '/scans', label: 'Scans' },
  { to: '/movers', label: 'Big movers' },
  { to: '/watchlists', label: 'Watchlists' },
  { to: '/alerts', label: 'Alerts' },
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
        <Route path="/movers" element={<MoversPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <AlertNotices />
    </AppShell>
  );
}

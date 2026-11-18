import { WatchlistPane } from '@/features/watchlists/WatchlistPane';
import { ChartPage } from './ChartPage';

/** Your watchlists: the chart page with the chosen list beside it instead of a scan's results. URL: `wl` (list id) + the chart's own params. */
export function WatchlistsPage() {
  return <ChartPage sidePane={(props) => <WatchlistPane {...props} />} />;
}

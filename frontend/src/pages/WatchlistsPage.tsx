import { SegmentedControl } from '@/components/ui';
import { WatchlistPane } from '@/features/watchlists/WatchlistPane';
import { WatchlistPerformance } from '@/features/watchlists/WatchlistPerformance';
import { useUrlState, useUrlUpdate } from '@/hooks/useUrlState';
import { ChartPage } from './ChartPage';

const VIEWS = [
  { value: 'chart' as const, label: 'Chart' },
  { value: 'perf' as const, label: 'Performance' },
];

/** Your watchlists: the chart page with the chosen list beside it, or how the list did since a date.
 * URL: `wl` (list id), `view` (chart/perf) + the chart's or the performance view's own params. */
export function WatchlistsPage() {
  const [view, setView] = useUrlState('view', 'chart');
  const update = useUrlUpdate();
  const perf = view === 'perf';
  const openChart = (id: number) => update({ view: undefined, instrument: String(id) });
  const viewSwitch = (
    <SegmentedControl value={perf ? 'perf' : 'chart'} options={VIEWS} onChange={setView} aria-label="Watchlist view" />
  );
  return (
    <ChartPage
      toolbarStart={viewSwitch}
      main={perf ? <WatchlistPerformance viewSwitch={viewSwitch} onOpenChart={openChart} /> : undefined}
      sidePane={(props) => (
        <WatchlistPane
          {...props}
          // In the Performance view, picking a stock opens its chart. The pane's own first-stock
          // pick (nothing charted yet) stays in the current view.
          onSelect={(id) => (perf && props.current !== undefined ? openChart(id) : props.onSelect(id))}
        />
      )}
    />
  );
}

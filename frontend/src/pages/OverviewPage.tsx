import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLiveQuotes, useMarketOverview, useSectorBreadth, useSectorRotation, useWatchlists } from '@/api/queries';
import type { MarketRow } from '@/api/types';
import { Button, EmptyState, ErrorMessage, Field, PageHeader, Select, TextInput } from '@/components/ui';
import { toListItems, useOpenChart } from '@/features/charts/chartList';
import { liveFigures, liveState, quoteMap } from '@/features/live/live';
import { LiveBadge } from '@/features/live/LiveBadge';
import { BenchmarkTiles } from '@/features/overview/BenchmarkTiles';
import { BreadthCard } from '@/features/overview/BreadthCard';
import { ScanCard } from '@/features/overview/ScanCard';
import { SectorBreadthCard, type SectorMode } from '@/features/overview/SectorBreadthCard';
import { SectorCard } from '@/features/overview/SectorCard';
import { agoCodec, agoValueError } from '@/features/scans/filterTree';
import {
  DEFAULT_MAS,
  DEFAULT_NEAR,
  DEFAULT_ROTATION_AGO,
  DEFAULT_ROTATION_MA,
  STOCK_UNIVERSES,
  sectorHref,
  toHighBasis,
  toRankBy,
} from '@/features/sectors/sectorLinks';
import '@/features/overview/overview.css';
import { intCodec, intListCodec, numberCodec, useUrlState, useUrlUpdate } from '@/hooks/useUrlState';
import { fmt } from '@/lib/format';


export function OverviewPage() {
  const [universe, setUniverse] = useUrlState('universe', 'nifty500');
  const [asOf, setAsOf] = useUrlState('as_of');
  // Sector breadth settings live in the URL so Back from a sector page restores them.
  const [mas, setMas] = useUrlState('ma', DEFAULT_MAS, intListCodec);
  const [minStocks, setMinStocks] = useUrlState('min', 5, intCodec);
  const [sectorView, setSectorView] = useUrlState('sector_view', 'latest');
  const [rotationMa, setRotationMa] = useUrlState('rotation_ma', DEFAULT_ROTATION_MA, intCodec);
  const [rotationAgo, setRotationAgo] = useUrlState('ago', DEFAULT_ROTATION_AGO, agoCodec);
  const [rankByRaw, setRankBy] = useUrlState('rank_by', 'ma');
  const [nearPct] = useUrlState('near_pct', DEFAULT_NEAR.pct, numberCodec);
  const [nearBasis] = useUrlState('near_basis', DEFAULT_NEAR.basis);
  const sectorMode: SectorMode = sectorView === 'rotation' ? 'rotation' : 'latest';
  const rankBy = toRankBy(rankByRaw);
  const near = useMemo(
    () => ({ pct: nearPct > 0 && nearPct < 100 ? nearPct : DEFAULT_NEAR.pct, basis: toHighBasis(nearBasis) }),
    [nearPct, nearBasis],
  );
  // Both near-high params change together in one history update.
  const updateUrl = useUrlUpdate();
  const setNear = (next: { pct: number; basis: string }) =>
    updateUrl({
      near_pct: next.pct === DEFAULT_NEAR.pct ? undefined : String(next.pct),
      near_basis: next.basis === DEFAULT_NEAR.basis ? undefined : next.basis,
    });

  const navigate = useNavigate();

  const { data: watchlists = [] } = useWatchlists();
  const overview = useMarketOverview(universe, asOf || undefined);
  const periods = mas.length ? mas : DEFAULT_MAS;
  const breadth = useSectorBreadth(universe, periods, near, asOf || undefined);
  const rotationPeriod = Math.max(1, rotationMa);
  // An invalid look-back doesn't fetch, so the table keeps its last result under the hint.
  const rotation = useSectorRotation(universe, rankBy, rotationPeriod, near, rotationAgo, minStocks, asOf || undefined,
    sectorMode === 'rotation' && !agoValueError(rotationAgo));
  const data = overview.data;
  // Index tiles go live during market hours, and only on the latest session (never with "As of").
  const live = useLiveQuotes((data?.benchmarks ?? []).map((b) => b.instrument_id), !asOf);
  const quotes = useMemo(() => quoteMap(asOf ? undefined : live.data?.quotes), [asOf, live.data]);
  const liveBadge = liveState(
    asOf ? undefined : live.data?.status,
    (data?.benchmarks ?? []).some((b) => liveFigures(b.ts, quotes.get(b.instrument_id))),
  );
  const universeLabel = watchlists.find((w) => w.watchlist_id === universe)?.name ?? universe;
  const universeOptions = watchlists
    .filter((w) => STOCK_UNIVERSES.has(w.watchlist_id))
    .map((w) => ({ value: w.watchlist_id, label: w.name }));
  // Every list on this page opens the chart with that list alongside.
  const openChart = useOpenChart();
  const context = `Overview · ${universeLabel}${data?.as_of ? ` · ${fmt.longDate(data.as_of)}` : ''}`;
  const open = (title: string, rows: MarketRow[] | undefined) => (r: MarketRow, shown?: MarketRow[]) =>
    openChart(r.instrument_id, { title, context, items: toListItems(shown ?? rows ?? []) });

  return (
    <div className="page">
      <PageHeader
        title="Market overview"
        subtitle={
          data?.as_of
            ? `${asOf ? 'As of' : 'Latest session'} ${fmt.longDate(data.as_of)} · ${universeLabel} · ${data.universe.priced} of ${data.universe.members} stocks priced`
            : 'Loading…'
        }
        actions={
          <>
            {universeOptions.length > 0 && (
              <Field label="Universe">
                <Select value={universe} options={universeOptions} onChange={setUniverse} />
              </Field>
            )}
            <Field label="As of">
              <TextInput type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
            </Field>
            {asOf && <Button onClick={() => setAsOf('')}>Latest</Button>}
          </>
        }
      />

      <ErrorMessage error={overview.error} />

      {liveBadge && (
        <div className="live-badge-row">
          <LiveBadge state={liveBadge} />
        </div>
      )}
      <BenchmarkTiles
        rows={data?.benchmarks}
        loading={overview.isLoading}
        onSelect={open('Benchmarks', data?.benchmarks)}
        quotes={quotes}
        stale={liveBadge?.kind === 'lost'}
      />

      {data && !data.as_of ? (
        <EmptyState>
          No daily data for this universe yet. Run <code>markets update</code> (or wait for the nightly job).
        </EmptyState>
      ) : (
        <>
          <div className="overview-split">
            <BreadthCard breadth={data?.breadth} universeLabel={universeLabel} />
            <SectorCard rows={data?.sectors} onSelect={open('Sectors', data?.sectors)} />
          </div>
          <SectorBreadthCard
            mode={sectorMode}
            onModeChange={setSectorView}
            data={breadth.data}
            loading={breadth.isLoading}
            error={breadth.error}
            periods={periods}
            onPeriodsChange={setMas}
            near={near}
            onNearChange={setNear}
            rotation={{
              data: rotation.data,
              loading: rotation.isLoading,
              error: rotation.error,
              rankBy,
              onRankByChange: setRankBy,
              period: rotationPeriod,
              onPeriodChange: setRotationMa,
              ago: rotationAgo,
              onAgoChange: setRotationAgo,
            }}
            minStocks={minStocks}
            onMinStocksChange={setMinStocks}
            onSelect={(industry) =>
              navigate(
                sectorHref(industry, {
                  universe,
                  asOf: asOf || undefined,
                  mas: periods,
                  near,
                  rotation: sectorMode === 'rotation' ? { rankBy, period: rotationPeriod, ago: rotationAgo } : undefined,
                }),
              )
            }
          />
          <div className="overview-scans">
            {data?.scans.map((s) => <ScanCard key={s.name} scan={s} onSelect={open(s.title, s.rows)} />)}
          </div>
        </>
      )}
    </div>
  );
}

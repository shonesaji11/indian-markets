import { useNavigate } from 'react-router-dom';
import { useMarketOverview, useSectorBreadth, useWatchlists } from '@/api/queries';
import type { MarketRow } from '@/api/types';
import { Button, EmptyState, ErrorMessage, Field, PageHeader, Select, TextInput } from '@/components/ui';
import { BenchmarkTiles } from '@/features/overview/BenchmarkTiles';
import { BreadthCard } from '@/features/overview/BreadthCard';
import { ScanCard } from '@/features/overview/ScanCard';
import { SectorBreadthCard } from '@/features/overview/SectorBreadthCard';
import { SectorCard } from '@/features/overview/SectorCard';
import { DEFAULT_MAS, STOCK_UNIVERSES, sectorHref } from '@/features/sectors/sectorLinks';
import '@/features/overview/overview.css';
import { intCodec, intListCodec, useUrlState } from '@/hooks/useUrlState';
import { fmt } from '@/lib/format';


export function OverviewPage() {
  const [universe, setUniverse] = useUrlState('universe', 'nifty500');
  const [asOf, setAsOf] = useUrlState('as_of');
  // Sector breadth settings live in the URL so Back from a sector page restores them.
  const [mas, setMas] = useUrlState('ma', DEFAULT_MAS, intListCodec);
  const [minStocks, setMinStocks] = useUrlState('min', 5, intCodec);

  const navigate = useNavigate();
  const open = (r: MarketRow) => navigate(`/chart?instrument=${r.instrument_id}&interval=1d`);

  const { data: watchlists = [] } = useWatchlists();
  const overview = useMarketOverview(universe, asOf || undefined);
  const periods = mas.length ? mas : DEFAULT_MAS;
  const breadth = useSectorBreadth(universe, periods, asOf || undefined);
  const data = overview.data;
  const universeLabel = watchlists.find((w) => w.watchlist_id === universe)?.name ?? universe;
  const universeOptions = watchlists
    .filter((w) => STOCK_UNIVERSES.has(w.watchlist_id))
    .map((w) => ({ value: w.watchlist_id, label: w.name }));

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

      <BenchmarkTiles rows={data?.benchmarks} loading={overview.isLoading} onSelect={open} />

      {data && !data.as_of ? (
        <EmptyState>
          No daily data for this universe yet. Run <code>markets update</code> (or wait for the nightly job).
        </EmptyState>
      ) : (
        <>
          <div className="overview-split">
            <BreadthCard breadth={data?.breadth} universeLabel={universeLabel} />
            <SectorCard rows={data?.sectors} onSelect={open} />
          </div>
          <SectorBreadthCard
            data={breadth.data}
            loading={breadth.isLoading}
            error={breadth.error}
            periods={periods}
            onPeriodsChange={setMas}
            minStocks={minStocks}
            onMinStocksChange={setMinStocks}
            onSelect={(industry) => navigate(sectorHref(industry, { universe, asOf: asOf || undefined, mas: periods }))}
          />
          <div className="overview-scans">
            {data?.scans.map((s) => <ScanCard key={s.name} scan={s} onSelect={open} />)}
          </div>
        </>
      )}
    </div>
  );
}

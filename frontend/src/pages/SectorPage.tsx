import { useNavigate } from 'react-router-dom';
import { useWatchlists } from '@/api/queries';
import { Button, EmptyState, Field, PageHeader, TextInput, sortCodec } from '@/components/ui';
import { SectorStocksPanel, type StocksView } from '@/features/sectors/SectorStocksPanel';
import { DEFAULT_MAS, DEFAULT_SECTOR_SORT, DEFAULT_UNIVERSE, overviewHref } from '@/features/sectors/sectorLinks';
import { intCodec, intListCodec, useUrlState } from '@/hooks/useUrlState';

/** One sector's stocks (opened from the Overview's Sector breadth card). Everything is in the URL. */
export function SectorPage() {
  const [industry] = useUrlState('name');
  const [universe] = useUrlState('universe', DEFAULT_UNIVERSE);
  const [asOf, setAsOf] = useUrlState('as_of');
  const [mas] = useUrlState('ma', DEFAULT_MAS, intListCodec);
  const [view, setView] = useUrlState('view', 'table');
  const [page, setPage] = useUrlState('page', 1, intCodec);
  const [sort, setSort] = useUrlState('sort', DEFAULT_SECTOR_SORT, sortCodec);
  const navigate = useNavigate();

  const { data: watchlists = [] } = useWatchlists();
  const universeLabel =
    universe === 'all' ? 'All tracked' : (watchlists.find((w) => w.watchlist_id === universe)?.name ?? universe);
  const periods = mas.length ? mas : DEFAULT_MAS;

  if (!industry) {
    return (
      <div className="page">
        <EmptyState>Pick a sector from the Sector breadth card on the Overview page.</EmptyState>
      </div>
    );
  }

  return (
    <div className="page">
      <PageHeader
        title={industry}
        subtitle={`Sector · ${universeLabel} · daily bars${asOf ? ` · as of ${asOf}` : ' · latest session'}`}
        actions={
          <>
            <Field label="As of">
              <TextInput type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
            </Field>
            <Button onClick={() => navigate(overviewHref({ universe, asOf: asOf || undefined, mas: periods }))}>
              All sectors
            </Button>
          </>
        }
      />
      <SectorStocksPanel
        industry={industry}
        universe={universe}
        universeLabel={universeLabel}
        asOf={asOf || undefined}
        periods={periods}
        view={view as StocksView}
        onViewChange={setView}
        page={page}
        onPageChange={setPage}
        sort={sort}
        onSortChange={setSort}
      />
    </div>
  );
}

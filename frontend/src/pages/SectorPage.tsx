import { useNavigate } from 'react-router-dom';
import { useWatchlists } from '@/api/queries';
import { Button, EmptyState, Field, PageHeader, TextInput, sortCodec } from '@/components/ui';
import { SectorStocksPanel, type StocksView } from '@/features/sectors/SectorStocksPanel';
import { agoCodec } from '@/features/scans/filterTree';
import {
  DEFAULT_MAS,
  DEFAULT_ROTATION_AGO,
  DEFAULT_ROTATION_MA,
  DEFAULT_SECTOR_SORT,
  DEFAULT_UNIVERSE,
  overviewHref,
} from '@/features/sectors/sectorLinks';
import { intCodec, intListCodec, useUrlState } from '@/hooks/useUrlState';

/** One sector's stocks (opened from the Overview's Sector breadth card). Everything is in the URL. */
export function SectorPage() {
  const [industry] = useUrlState('name');
  const [universe] = useUrlState('universe', DEFAULT_UNIVERSE);
  const [asOf, setAsOf] = useUrlState('as_of');
  const [mas] = useUrlState('ma', DEFAULT_MAS, intListCodec);
  // Opened from the Rotation view: show its MA, and carry its settings back to the Overview.
  const [sectorView] = useUrlState('sector_view', 'latest');
  const [rotationMa] = useUrlState('rotation_ma', DEFAULT_ROTATION_MA, intCodec);
  const [rotationAgo] = useUrlState('ago', DEFAULT_ROTATION_AGO, agoCodec);
  const [view, setView] = useUrlState('view', 'table');
  const [page, setPage] = useUrlState('page', 1, intCodec);
  const [sort, setSort] = useUrlState('sort', DEFAULT_SECTOR_SORT, sortCodec);
  const navigate = useNavigate();

  const { data: watchlists = [] } = useWatchlists();
  const universeLabel =
    universe === 'all' ? 'All tracked' : (watchlists.find((w) => w.watchlist_id === universe)?.name ?? universe);
  const overviewMas = mas.length ? mas : DEFAULT_MAS;
  const rotation = sectorView === 'rotation' ? { period: Math.max(1, rotationMa), ago: rotationAgo } : undefined;
  const periods = rotation ? [rotation.period] : overviewMas;

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
            <Button onClick={() => navigate(overviewHref({ universe, asOf: asOf || undefined, mas: overviewMas, rotation }))}>
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

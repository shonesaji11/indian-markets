import { useMemo } from 'react';
import { useScanRun, useWatchlists } from '@/api/queries';
import type { SavedScan, ScanDefinition } from '@/api/types';
import { Card, Checkbox, ErrorMessage, Field, PageHeader, Select, TextInput, sortCodec, type SortState } from '@/components/ui';
import { FilterBuilder } from '@/features/scans/FilterBuilder';
import { EMPTY_FILTER, filterCodec, prune } from '@/features/scans/filterTree';
import { SavedScans } from '@/features/scans/SavedScans';
import { DEFAULT_UNIVERSE, STOCK_UNIVERSES } from '@/features/sectors/sectorLinks';
import { ScanResultsTable } from '@/features/scans/ScanResultsTable';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { boolCodec, useUrlState, useUrlUpdate } from '@/hooks/useUrlState';
import { fmt } from '@/lib/format';

const DEFAULT_SORT: SortState = { key: 'symbol' };

export function ScansPage() {
  // Everything lives in the URL: Back from a chart, reloads and shared links restore the exact scan.
  const [filter, setFilter] = useUrlState('f', EMPTY_FILTER, filterCodec);
  const [universe, setUniverse] = useUrlState('universe', DEFAULT_UNIVERSE);
  const [asOf, setAsOf] = useUrlState('as_of');
  const [includeIndices, setIncludeIndices] = useUrlState('idx', false, boolCodec);
  const [sort, setSort] = useUrlState('sort', DEFAULT_SORT, sortCodec);
  const [savedId] = useUrlState('scan');
  const update = useUrlUpdate();

  const definition: ScanDefinition = useMemo(
    () => ({ filter, universe, include_indices: includeIndices }),
    [filter, universe, includeIndices],
  );
  // Wait for typing to settle, and don't send half-filled conditions.
  const request = useDebouncedValue(
    useMemo(() => ({ ...definition, filter: prune(filter), as_of: asOf || undefined }), [definition, filter, asOf]),
    300,
  );
  const result = useScanRun(request);
  const data = result.data;

  const { data: watchlists = [] } = useWatchlists();
  const universeOptions = [
    ...watchlists.filter((w) => STOCK_UNIVERSES.has(w.watchlist_id)).map((w) => ({ value: w.watchlist_id, label: w.name })),
    { value: 'all', label: 'All tracked' },
  ];

  // A saved scan brings its universe and index toggle; "New scan" only clears the conditions.
  const load = (scan: SavedScan | undefined) =>
    update(
      scan
        ? {
            scan: scan.scan_id,
            f: filterCodec.format(scan.definition.filter),
            universe: scan.definition.universe !== DEFAULT_UNIVERSE ? scan.definition.universe : undefined,
            idx: scan.definition.include_indices ? '1' : undefined,
          }
        : { scan: undefined, f: undefined },
    );

  return (
    <div className="page">
      <PageHeader title="Scans" subtitle="Combine conditions on prices, volumes and indicators across a universe, as of any date." />

      <Card
        title="Filters"
        subtitle="Every condition is evaluated on daily (1d) bars, at each stock's last session up to the As of date."
        actions={
          <>
            <Field label="Universe">
              <Select value={universe} options={universeOptions} onChange={setUniverse} />
            </Field>
            <Field label="As of">
              <TextInput type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
            </Field>
            <Field label="Indices">
              <Checkbox checked={includeIndices} onChange={setIncludeIndices}>
                Include
              </Checkbox>
            </Field>
          </>
        }
        divided
      >
        <FilterBuilder value={filter} onChange={setFilter} />
        <div className="ui-row" style={{ marginTop: 16 }}>
          <SavedScans current={savedId} definition={definition} onLoad={load} />
        </div>
      </Card>

      <Card
        title="Results"
        subtitle={
          result.isFetching
            ? 'Running…'
            : data
              ? `${data.universe.matched} of ${data.universe.priced} instruments · ${data.timeframe} bars${data.as_of ? ` · ${fmt.longDate(data.as_of)}` : ''}`
              : undefined
        }
        divided
        flush
      >
        <ErrorMessage error={result.error} />
        <ScanResultsTable
          rows={data?.rows ?? []}
          extra={data?.columns ?? []}
          sort={sort}
          onSortChange={setSort}
          empty={result.isLoading ? 'Running…' : undefined}
        />
      </Card>
    </div>
  );
}

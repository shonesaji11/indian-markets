import { useMemo } from 'react';
import { useSavedScans, useScanPerformance, useScanRun, useWatchlists } from '@/api/queries';
import type { SavedScan, ScanDefinition } from '@/api/types';
import { Card, Checkbox, ErrorMessage, Field, PageHeader, Select, TextInput, sortCodec, type SortState } from '@/components/ui';
import { BasketPerformance, performanceColumns, performanceTitle } from '@/features/scans/BasketPerformance';
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
  const [until, setUntil] = useUrlState('until');
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

  // A scan on a past day: how its results did from that day's close up to Until (default latest).
  const untilError = asOf && until && until < asOf ? 'Until must be after the As of date.' : null;
  const perfRequest = useMemo(
    () =>
      asOf && !untilError && data?.as_of && data.rows.length && !result.isPlaceholderData
        ? { instrument_ids: data.rows.map((r) => r.instrument_id), start: data.as_of.slice(0, 10), end: until || undefined }
        : undefined,
    [asOf, until, untilError, data, result.isPlaceholderData],
  );
  const perf = useScanPerformance(perfRequest);
  const perfTitle = perf.data ? performanceTitle(perf.data, Boolean(until)) : '';
  const perfColumns = useMemo(() => performanceColumns(perf.data, perfTitle), [perf.data, perfTitle]);
  const showPerf = perfRequest !== undefined && (perf.isLoading || perf.error || (perf.data?.sessions ?? 0) > 0);

  const { data: watchlists = [] } = useWatchlists();
  const universeOptions = [
    ...watchlists.filter((w) => STOCK_UNIVERSES.has(w.watchlist_id)).map((w) => ({ value: w.watchlist_id, label: w.name })),
    { value: 'all', label: 'All tracked' },
  ];
  const { data: saved = [] } = useSavedScans();
  const universeLabel = universeOptions.find((o) => o.value === universe)?.label ?? universe;
  const list = {
    title: saved.find((s) => s.scan_id === savedId)?.name ?? 'Scan results',
    context: `Scans · ${universeLabel}${data?.as_of ? ` · ${fmt.longDate(data.as_of)}` : ''}`,
  };

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
            {asOf && (
              <Field label="Until">
                <TextInput type="date" value={until} min={asOf} onChange={(e) => setUntil(e.target.value)} />
                {untilError && <span className="scan-perf__error">{untilError}</span>}
              </Field>
            )}
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

      {showPerf && (
        <BasketPerformance perf={perf.data} loading={perf.isLoading} error={perf.error} title={perfTitle} />
      )}

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
          list={list}
          sort={sort}
          onSortChange={setSort}
          empty={result.isLoading ? 'Running…' : undefined}
          afterChange={perfColumns}
        />
      </Card>
    </div>
  );
}

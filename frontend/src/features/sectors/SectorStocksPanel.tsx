import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useScanRun } from '@/api/queries';
import type { ScanOperand, ScanRow } from '@/api/types';
import { Card, ErrorMessage, SegmentedControl, sortRows, type SortState } from '@/components/ui';
import { ChartGrid, type GridItem } from '@/features/charts/ChartGrid';
import { EMPTY_FILTER } from '@/features/scans/filterTree';
import { ScanResultsTable } from '@/features/scans/ScanResultsTable';

export type StocksView = 'table' | 'charts';

const VIEW_OPTIONS = [
  { value: 'table' as const, label: 'Table' },
  { value: 'charts' as const, label: 'Charts' },
];

interface SectorStocksPanelProps {
  industry: string;
  universe: string;
  asOf?: string;
  periods: number[];
  view: StocksView;
  onViewChange: (v: StocksView) => void;
  page: number;
  onPageChange: (p: number) => void;
  sort: SortState;
  onSortChange: (s: SortState) => void;
}

/** Every stock in one sector with its SMAs, as a table or a grid of mini charts; both open the full chart. */
export function SectorStocksPanel(props: SectorStocksPanelProps) {
  const { industry, universe, asOf, periods, view, onViewChange, page, onPageChange, sort, onSortChange } = props;
  const navigate = useNavigate();
  const open = (instrumentId: number) => navigate(`/chart?instrument=${instrumentId}&interval=1d`);

  const columns = useMemo<ScanOperand[]>(
    () => periods.map((p) => ({ type: 'indicator', name: 'sma', params: { period: p, source: 'close' }, output: 'sma' })),
    [periods],
  );
  const result = useScanRun({
    filter: EMPTY_FILTER,
    universe,
    include_indices: false,
    as_of: asOf,
    industry,
    columns,
  });
  const rows = result.data?.rows ?? [];

  // The grid follows the table's sort so switching views keeps the same order.
  const items: GridItem[] = useMemo(() => {
    const get = (r: ScanRow) => (sort.key === 'symbol' ? r.symbol : (r[sort.key] as number | string | null));
    return sortRows(rows, get, sort.desc).map((r) => ({
      instrument_id: r.instrument_id,
      title: r.symbol.replace(/-EQ$/, ''),
      price: r.close,
      change: r.pct_change,
    }));
  }, [rows, sort]);
  // Column i of the response is the SMA for periods[i].
  const above = (i: number) => {
    const key = result.data?.columns[i]?.key;
    return key ? rows.filter((r) => typeof r[key] === 'number' && r.close > (r[key] as number)).length : 0;
  };

  return (
    <Card
      title="Stocks"
      subtitle={
        result.isFetching
          ? 'Loading…'
          : `${rows.length} stocks · ${periods.map((p, i) => `${above(i)} above ${p} MA`).join(' · ')}`
      }
      actions={<SegmentedControl value={view} options={VIEW_OPTIONS} onChange={onViewChange} aria-label="Show stocks as" />}
      divided
      flush
    >
      <ErrorMessage error={result.error} />
      {view === 'charts' ? (
        <ChartGrid items={items} onSelect={(i) => open(i.instrument_id)} page={page} onPageChange={onPageChange} />
      ) : (
        <ScanResultsTable
          rows={rows}
          extra={result.data?.columns ?? []}
          sort={sort}
          onSortChange={onSortChange}
          empty={result.isLoading ? 'Loading…' : undefined}
        />
      )}
    </Card>
  );
}

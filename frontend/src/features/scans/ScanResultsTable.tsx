import { useMemo } from 'react';
import type { ScanColumn, ScanRow } from '@/api/types';
import { DataTable, Delta, type Column, type SortState } from '@/components/ui';
import { toListItems, useOpenChart, type ChartListInfo } from '@/features/charts/chartList';
import { fmt } from '@/lib/format';
import { formatDate } from '@/lib/time';

const signed = (v: number | null) => <Delta value={v} format={fmt.pctAbs} />;
const num = (row: ScanRow, key: string) => (typeof row[key] === 'number' ? (row[key] as number) : null);

const BASE: Column<ScanRow>[] = [
  { key: 'symbol', header: 'Instrument', value: (r) => `${r.exchange}:${r.symbol}` },
  { key: 'ts', header: 'Date', value: (r) => r.ts, render: (r) => formatDate(r.ts) },
  { key: 'close', header: 'Close', value: (r) => r.close, render: (r) => fmt.price(r.close), align: 'right' },
  { key: 'pct_change', header: 'Change', value: (r) => r.pct_change, render: (r) => signed(r.pct_change), align: 'right' },
  { key: 'high_52w', header: '52w high', value: (r) => r.high_52w, render: (r) => fmt.price(r.high_52w), align: 'right' },
  { key: 'low_52w', header: '52w low', value: (r) => r.low_52w, render: (r) => fmt.price(r.low_52w), align: 'right' },
  { key: 'from_high_52w', header: 'From high', value: (r) => r.from_high_52w, render: (r) => signed(r.from_high_52w), align: 'right' },
  { key: 'volume', header: 'Volume', value: (r) => r.volume, render: (r) => fmt.compact(r.volume), align: 'right' },
  { key: 'relative_volume', header: 'Rel. volume', value: (r) => r.relative_volume, render: (r) => fmt.ratio(r.relative_volume), align: 'right' },
];

interface ScanResultsTableProps {
  rows: ScanRow[];
  /** Operands used by the filter; ones not already shown get their own column. */
  extra: ScanColumn[];
  /** Names the list shown beside the chart a row opens. */
  list: ChartListInfo;
  sort: SortState;
  onSortChange: (s: SortState) => void;
  /** Shown instead of rows when there are none (defaults to a no-matches message). */
  empty?: string;
}

/** Matched instruments; clicking a row opens its chart with the rows alongside, in the order shown (Back returns to the scan). */
export function ScanResultsTable({ rows, extra, list, sort, onSortChange, empty = 'No instruments match these conditions.' }: ScanResultsTableProps) {
  const openChart = useOpenChart();
  const columns = useMemo(() => {
    const shown = new Set(BASE.map((c) => c.key));
    const added: Column<ScanRow>[] = extra
      .filter((c) => !shown.has(c.key))
      .map((c) => ({
        key: c.key,
        header: c.label,
        value: (r) => num(r, c.key),
        render: (r) => (c.percent ? signed(num(r, c.key)) : fmt.price(num(r, c.key))),
        align: 'right',
      }));
    return [...BASE, ...added];
  }, [extra]);

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.instrument_id}
      onRowClick={(r, shown) => openChart(r.instrument_id, { ...list, items: toListItems(shown) })}
      sort={sort}
      onSortChange={onSortChange}
      empty={empty}
    />
  );
}

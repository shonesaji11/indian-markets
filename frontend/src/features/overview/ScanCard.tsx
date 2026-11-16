import type { MarketRow, ScanResult } from '@/api/types';
import { Card, DataTable, Delta, type Column } from '@/components/ui';
import { fmt } from '@/lib/format';

/** The extra column each scan shows to explain why a stock is listed. */
const EXTRA: Record<string, Column<MarketRow>> = {
  volume_shockers: {
    key: 'rvol',
    header: 'Rel. vol',
    value: (r) => r.relative_volume,
    render: (r) => <b className="num">{fmt.ratio(r.relative_volume)}</b>,
    align: 'right',
  },
  gap_ups: { key: 'gap', header: 'Gap', value: (r) => r.gap_pct, render: (r) => <Delta value={r.gap_pct} format={fmt.pctAbs} />, align: 'right' },
  gap_downs: { key: 'gap', header: 'Gap', value: (r) => r.gap_pct, render: (r) => <Delta value={r.gap_pct} format={fmt.pctAbs} />, align: 'right' },
  new_52w_lows: { key: 'low', header: '52W low', value: (r) => r.low_52w, render: (r) => fmt.price(r.low_52w), align: 'right' },
  new_52w_highs: { key: 'high', header: '52W high', value: (r) => r.high_52w, render: (r) => fmt.price(r.high_52w), align: 'right' },
};
const VOLUME: Column<MarketRow> = { key: 'vol', header: 'Volume', value: (r) => r.volume, render: (r) => fmt.compact(r.volume), align: 'right' };

const BASE: Column<MarketRow>[] = [
  {
    key: 'symbol',
    header: 'Stock',
    value: (r) => r.symbol,
    render: (r) => (
      <div className="scan-stock">
        <span className="scan-stock__symbol">{r.symbol.replace(/-EQ$/, '')}</span>
        <span className="scan-stock__meta">{r.industry ?? r.name}</span>
      </div>
    ),
  },
  { key: 'close', header: 'Price', value: (r) => r.close, render: (r) => fmt.price(r.close), align: 'right' },
  {
    key: 'chg',
    header: 'Change',
    value: (r) => r.pct_change,
    render: (r) => <Delta value={r.pct_change} format={fmt.pctAbs} pill />,
    align: 'right',
  },
];

interface ScanCardProps {
  scan: ScanResult;
  onSelect?: (row: MarketRow) => void;
}

export function ScanCard({ scan, onSelect }: ScanCardProps) {
  const columns = [...BASE, EXTRA[scan.name] ?? VOLUME];
  return (
    <Card title={scan.title} subtitle={scan.description} divided flush>
      <DataTable
        dense
        columns={columns}
        rows={scan.rows}
        rowKey={(r) => r.instrument_id}
        onRowClick={onSelect}
        empty="Nothing qualifies on this day"
      />
    </Card>
  );
}

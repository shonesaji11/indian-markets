import type { MarketRow } from '@/api/types';
import { Card, Delta, DivergingBars } from '@/components/ui';
import { fmt } from '@/lib/format';

const short = (symbol: string) => symbol.replace(/^Nifty\s+/i, '');

export function SectorCard({ rows, onSelect }: { rows: MarketRow[] | undefined; onSelect?: (row: MarketRow) => void }) {
  const list = rows ?? [];
  return (
    <Card title="Sectors" subtitle="NSE sectoral indices, % change on the day">
      <DivergingBars
        items={list.map((r) => ({ key: r.instrument_id, label: short(r.symbol), value: r.pct_change }))}
        format={(v) => <Delta value={v} format={fmt.pctAbs} />}
        onSelect={onSelect ? (item) => onSelect(list.find((r) => r.instrument_id === item.key)!) : undefined}
      />
    </Card>
  );
}

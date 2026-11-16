import { useMemo } from 'react';
import type { MarketRow } from '@/api/types';
import { Delta, Skeleton, Sparkline, StatTile } from '@/components/ui';
import { useThemeVersion } from '@/hooks/useTheme';
import { cssVar, fmt } from '@/lib/format';

interface BenchmarkTilesProps {
  rows: MarketRow[] | undefined;
  loading?: boolean;
  onSelect?: (row: MarketRow) => void;
}

const DISPLAY_NAMES: Record<string, string> = {
  'Nifty 50': 'Nifty 50',
  SENSEX: 'Sensex',
  'Nifty Bank': 'Bank Nifty',
  'NIFTY MIDCAP 100': 'Midcap 100',
  'NIFTY SMLCAP 100': 'Smallcap 100',
  'India VIX': 'India VIX',
};

export function BenchmarkTiles({ rows, loading, onSelect }: BenchmarkTilesProps) {
  const themeVersion = useThemeVersion();
  const lineColor = useMemo(() => cssVar('--series-1'), [themeVersion]);

  if (loading && !rows) {
    return (
      <div className="overview-tiles">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="ui-stat">
            <Skeleton width="50%" />
            <Skeleton width="70%" height={24} style={{ marginTop: 6 }} />
            <Skeleton height={36} style={{ marginTop: 10 }} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="overview-tiles">
      {(rows ?? []).map((r) => (
        <StatTile
          key={r.instrument_id}
          label={DISPLAY_NAMES[r.symbol] ?? r.symbol}
          value={<span className="num">{fmt.price(r.close)}</span>}
          delta={<Delta value={r.pct_change} format={fmt.pctAbs} arrow />}
          note={<Delta value={r.change} format={fmt.price} />}
          onClick={onSelect ? () => onSelect(r) : undefined}
          title={`${r.exchange}:${r.symbol} · open chart`}
        >
          <Sparkline
            points={(r.spark ?? []).map((p) => ({ label: fmt.shortDate(p.ts), value: p.close }))}
            color={lineColor}
            formatValue={fmt.price}
          />
        </StatTile>
      ))}
    </div>
  );
}

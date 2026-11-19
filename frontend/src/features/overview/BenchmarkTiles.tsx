import { useMemo } from 'react';
import type { LiveQuote, MarketRow } from '@/api/types';
import { Delta, FlashValue, Skeleton, Sparkline, StatTile } from '@/components/ui';
import { liveFigures } from '@/features/live/live';
import { useThemeVersion } from '@/hooks/useTheme';
import { cssVar, fmt } from '@/lib/format';

interface BenchmarkTilesProps {
  rows: MarketRow[] | undefined;
  loading?: boolean;
  onSelect?: (row: MarketRow) => void;
  /** Live quotes by instrument: shown instead of the stored bar while newer than it. */
  quotes?: Map<number, LiveQuote>;
  /** The live feed is down: live prices are greyed as possibly old. */
  stale?: boolean;
}

const DISPLAY_NAMES: Record<string, string> = {
  'Nifty 50': 'Nifty 50',
  SENSEX: 'Sensex',
  'Nifty Bank': 'Bank Nifty',
  'NIFTY MIDCAP 100': 'Midcap 100',
  'NIFTY SMLCAP 100': 'Smallcap 100',
  'India VIX': 'India VIX',
};

export function BenchmarkTiles({ rows, loading, onSelect, quotes, stale = false }: BenchmarkTilesProps) {
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
      {(rows ?? []).map((r) => {
        const live = liveFigures(r.ts, quotes?.get(r.instrument_id));
        const close = live?.close ?? r.close;
        const spark = (r.spark ?? []).map((p) => ({ label: fmt.shortDate(p.ts), value: p.close }));
        if (live) spark.push({ label: `${fmt.shortDate(live.ts)} live`, value: live.close });
        return (
          <StatTile
            key={r.instrument_id}
            label={DISPLAY_NAMES[r.symbol] ?? r.symbol}
            value={
              <FlashValue value={close}>
                <span className={live && stale ? 'num muted' : 'num'}>{fmt.price(close)}</span>
              </FlashValue>
            }
            delta={<Delta value={live ? live.pct_change : r.pct_change} format={fmt.pctAbs} arrow />}
            note={<Delta value={live ? live.change : r.change} format={fmt.price} />}
            onClick={onSelect ? () => onSelect(r) : undefined}
            title={`${r.exchange}:${r.symbol} · open chart`}
          >
            <Sparkline points={spark} color={lineColor} formatValue={fmt.price} liveLast={!!live} />
          </StatTile>
        );
      })}
    </div>
  );
}

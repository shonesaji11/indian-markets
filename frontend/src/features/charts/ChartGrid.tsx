import { useMemo } from 'react';
import { useCandles } from '@/api/queries';
import { PriceChart, toOhlc } from '@/components/charts';
import { Button, Delta, EmptyState, Skeleton } from '@/components/ui';
import { useElementWidth } from '@/hooks/useElementWidth';
import { fmt } from '@/lib/format';
import './charts.css';

export interface GridItem {
  instrument_id: number;
  title: string;
  /** Last close and day's change (fraction), shown in the tile header since tiles have no price axis. */
  price?: number | null;
  change?: number | null;
}

interface ChartGridProps {
  items: GridItem[];
  onSelect: (item: GridItem) => void;
  page: number;
  onPageChange: (page: number) => void;
  /** Rows per page; columns are as many as fit (tiles at least TILE_MIN_WIDTH wide), so pages are always full. */
  rows?: number;
  /** How much history each tile shows, in months of daily bars. */
  months?: number;
}

const TILE_MIN_WIDTH = 240;
const GAP = 12; // matches --space-3 in charts.css

/** Miniature daily candlestick charts for quickly eyeballing price action. Only the visible page loads. */
export function ChartGrid({ items, onSelect, page, onPageChange, rows = 4, months = 6 }: ChartGridProps) {
  const [tilesRef, width] = useElementWidth<HTMLDivElement>();
  const columns = Math.max(1, Math.floor((width + GAP) / (TILE_MIN_WIDTH + GAP)));
  const pageSize = columns * rows;
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  const current = Math.min(Math.max(page, 1), pages);
  const visible = items.slice((current - 1) * pageSize, current * pageSize);
  const start = useMemo(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - months);
    return d.toISOString().slice(0, 10);
  }, [months]);

  if (items.length === 0) return <EmptyState>No instruments to chart.</EmptyState>;

  return (
    <div className="chart-grid">
      {pages > 1 && (
        <div className="ui-row chart-grid__pager">
          <span className="muted">
            {(current - 1) * pageSize + 1}–{(current - 1) * pageSize + visible.length} of {items.length}
          </span>
          <Button size="sm" icon disabled={current <= 1} onClick={() => onPageChange(current - 1)} aria-label="Previous page">
            ‹
          </Button>
          <Button size="sm" icon disabled={current >= pages} onClick={() => onPageChange(current + 1)} aria-label="Next page">
            ›
          </Button>
        </div>
      )}
      <div ref={tilesRef} className="chart-grid__tiles" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
        {/* Wait for the first measurement so a wrong page size doesn't fetch extra charts. */}
        {width > 0 && visible.map((item) => (
          <MiniChart key={item.instrument_id} item={item} start={start} onSelect={onSelect} />
        ))}
      </div>
      {/* Tiles hide lightweight-charts' logo; its licence asks for attribution, given here once. */}
      <div className="muted chart-grid__credit">
        Charts by{' '}
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
          TradingView
        </a>
      </div>
    </div>
  );
}

function MiniChart({ item, start, onSelect }: { item: GridItem; start: string; onSelect: (item: GridItem) => void }) {
  const candles = useCandles(item.instrument_id, '1d', start);
  const ohlc = useMemo(() => toOhlc(candles.data?.candles ?? []), [candles.data]);

  return (
    <button type="button" className="chart-grid__tile" onClick={() => onSelect(item)} title={`Open ${item.title}`}>
      <span className="chart-grid__head">
        <span className="chart-grid__title">{item.title}</span>
        <span className="chart-grid__quote">
          {item.price != null && <span className="num">{fmt.price(item.price)}</span>}
          {item.change != null && <Delta value={item.change} format={fmt.pctAbs} />}
        </span>
      </span>
      {candles.isLoading ? <Skeleton height={150} /> : <PriceChart candles={ohlc} height={150} compact />}
    </button>
  );
}

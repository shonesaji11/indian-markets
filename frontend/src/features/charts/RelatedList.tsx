import { useEffect, useRef, type ReactNode } from 'react';
import { Button, Delta } from '@/components/ui';
import { fmt } from '@/lib/format';
import { shortSymbol, type ChartList } from './chartList';
import './charts.css';

/** What the chart page hands its side pane (this list, or the Watchlists tab's pane). */
export interface SidePaneProps {
  current: number | undefined;
  onSelect: (instrumentId: number) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface RelatedListProps extends SidePaneProps {
  list: ChartList;
  /** Replaces the title with your own controls (e.g. the watchlist picker). */
  toolbar?: ReactNode;
  /** Adds a ✕ to each row that calls this. */
  onRemove?: (instrumentId: number) => void;
  /** Shown instead of the rows when the list is empty. */
  empty?: ReactNode;
}

const isTyping = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName));

/** The list a chart was opened from; click a stock, or use ↑/↓ (J/K), to chart the next one. */
export function RelatedList({ list, current, onSelect, open, onOpenChange, toolbar, onRemove, empty }: RelatedListProps) {
  const { items } = list;
  const index = items.findIndex((i) => i.instrument_id === current);
  const activeRef = useRef<HTMLButtonElement>(null);

  // -1 (current stock not in the list, e.g. picked by search) steps to the first or last.
  const step = (by: number) => {
    const next = index < 0 ? (by > 0 ? 0 : items.length - 1) : index + by;
    if (next >= 0 && next < items.length) onSelect(items[next].instrument_id);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
      const by = e.key === 'ArrowDown' || e.key === 'j' ? 1 : e.key === 'ArrowUp' || e.key === 'k' ? -1 : 0;
      if (!by) return;
      e.preventDefault();
      step(by);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest' });
  }, [current, open]);

  if (!open) {
    return (
      <button className="chart-list chart-list--closed" onClick={() => onOpenChange(true)} title="Show the list">
        <span>
          {list.title} · {items.length}
        </span>
      </button>
    );
  }

  return (
    <aside className="chart-list">
      {toolbar && <div className="chart-list__toolbar">{toolbar}</div>}
      <header className="chart-list__head">
        <div style={{ minWidth: 0 }}>
          {!toolbar && <div className="chart-list__title">{list.title}</div>}
          <div className="muted chart-list__meta">
            {list.context ? `${list.context} · ` : ''}
            {index >= 0 ? `${index + 1} of ${items.length}` : `${items.length} stocks`}
          </div>
        </div>
        <div className="ui-row chart-list__nav">
          <Button size="sm" icon onClick={() => step(-1)} disabled={index === 0} title="Previous (↑ or K)">
            ‹
          </Button>
          <Button size="sm" icon onClick={() => step(1)} disabled={index === items.length - 1} title="Next (↓ or J)">
            ›
          </Button>
          <Button size="sm" icon onClick={() => onOpenChange(false)} title="Hide the list">
            ×
          </Button>
        </div>
      </header>
      <div className="chart-list__items">
        {items.length === 0 && empty}
        {items.map((item, i) => (
          <div key={item.instrument_id} className="chart-list__row">
            <button
              ref={i === index ? activeRef : undefined}
              className="chart-list__item"
              data-active={i === index}
              onClick={() => onSelect(item.instrument_id)}
            >
              <span className="chart-list__symbol" title={item.note ? `${item.symbol} · last bar ${item.note}` : undefined}>
                {shortSymbol(item.symbol)}
                {item.note && <span className="muted chart-list__note"> · {item.note}</span>}
              </span>
              {item.close !== undefined && <span className="num chart-list__close">{fmt.price(item.close)}</span>}
              <Delta value={item.change} format={fmt.pctAbs} />
            </button>
            {onRemove && (
              <button
                className="chart-list__remove"
                title={`Remove ${shortSymbol(item.symbol)} from the list`}
                aria-label={`Remove ${shortSymbol(item.symbol)}`}
                onClick={() => onRemove(item.instrument_id)}
              >
                ✕
              </button>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}

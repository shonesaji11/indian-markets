import { useEffect, useRef } from 'react';
import { Button, Delta } from '@/components/ui';
import { fmt } from '@/lib/format';
import { shortSymbol, type ChartList } from './chartList';
import './charts.css';

interface RelatedListProps {
  list: ChartList;
  current: number | undefined;
  onSelect: (instrumentId: number) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const isTyping = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName));

/** The list a chart was opened from; click a stock, or use ↑/↓ (J/K), to chart the next one. */
export function RelatedList({ list, current, onSelect, open, onOpenChange }: RelatedListProps) {
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
      <header className="chart-list__head">
        <div style={{ minWidth: 0 }}>
          <div className="chart-list__title">{list.title}</div>
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
        {items.map((item, i) => (
          <button
            key={item.instrument_id}
            ref={i === index ? activeRef : undefined}
            className="chart-list__item"
            data-active={i === index}
            onClick={() => onSelect(item.instrument_id)}
          >
            <span className="chart-list__symbol">{shortSymbol(item.symbol)}</span>
            <Delta value={item.change} format={fmt.pctAbs} />
          </button>
        ))}
      </div>
    </aside>
  );
}

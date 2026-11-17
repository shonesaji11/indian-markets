import { useState } from 'react';
import { fmt } from '@/lib/format';
import { loadSetting, saveSetting } from '@/lib/storage';
import './ChartLegend.css';

export interface LegendItem {
  key: string;
  label: string;
  color: string;
  /** One value per output; undefined where the series has no point at that bar. */
  values: (number | undefined)[];
}

/** Whether the legend is expanded (remembered per browser). */
const OPEN_KEY = 'markets.chart.legendOpen';

/** Collapsible indicator legend laid over the top-left of a chart. */
export function ChartLegend({ items }: { items: LegendItem[] }) {
  const [open, setOpenState] = useState(() => loadSetting(OPEN_KEY) !== '0');
  if (items.length === 0) return null;
  const toggle = () => {
    saveSetting(OPEN_KEY, open ? '0' : null);
    setOpenState(!open);
  };
  return (
    <div className="chart-legend">
      <button type="button" className="chart-legend__toggle" aria-expanded={open} onClick={toggle}>
        {open ? '▾' : '▸'} Indicators{open ? '' : ` (${items.length})`}
      </button>
      {open &&
        items.map((item) => (
          <div key={item.key} className="chart-legend__row">
            <span className="chart-legend__dot" style={{ background: item.color }} />
            <span className="chart-legend__label">{item.label}</span>
            <span className="num">{item.values.map((v) => (v == null ? '—' : fmt.price(v))).join(' · ')}</span>
          </div>
        ))}
    </div>
  );
}

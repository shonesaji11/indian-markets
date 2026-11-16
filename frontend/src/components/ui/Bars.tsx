import type { ReactNode } from 'react';

interface MeterProps {
  label: ReactNode;
  /** 0..1 */
  value: number | null | undefined;
  format?: (v: number) => string;
}

/** A single share on a 0–100% track. */
export function Meter({ label, value, format = (v) => `${Math.round(v * 100)}%` }: MeterProps) {
  const pct = value == null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="ui-meter">
      <span className="ui-meter__label">{label}</span>
      <span className="ui-meter__value">{value == null ? '–' : format(value)}</span>
      <div className="ui-meter__track" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <div className="ui-meter__fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export interface Segment {
  key: string;
  label: string;
  value: number;
  color: string;
}

/** Part-to-whole on one track, with a legend that always states the counts. */
export function SegmentBar({ segments }: { segments: Segment[] }) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <div>
      <div className="ui-segbar__track">
        {segments
          .filter((s) => s.value > 0)
          .map((s) => (
            <div
              key={s.key}
              className="ui-segbar__seg"
              style={{ width: `${(s.value / total) * 100}%`, background: s.color }}
              title={`${s.label}: ${s.value}`}
            />
          ))}
      </div>
      <div className="ui-segbar__legend">
        {segments.map((s) => (
          <span key={s.key} className="ui-segbar__key">
            <span className="ui-swatch" style={{ background: s.color }} />
            {s.label} <b>{s.value}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

export interface DivergingItem {
  key: string | number;
  label: string;
  value: number | null;
}

interface DivergingBarsProps {
  items: DivergingItem[];
  format: (v: number) => ReactNode;
  onSelect?: (item: DivergingItem) => void;
}

/** Positive/negative values from a shared zero line, labelled with their values. */
export function DivergingBars({ items, format, onSelect }: DivergingBarsProps) {
  const max = Math.max(...items.map((i) => Math.abs(i.value ?? 0)), 1e-9);
  return (
    <div className="ui-dbars">
      {items.map((item) => {
        const v = item.value ?? 0;
        const width = `${(Math.abs(v) / max) * 50}%`;
        return (
          <div key={item.key} className="ui-dbars__row" onClick={onSelect ? () => onSelect(item) : undefined}>
            <span className="ui-dbars__label" title={item.label}>
              {item.label}
            </span>
            <span className="ui-dbars__track">
              <span className={`ui-dbars__bar ui-dbars__bar--${v >= 0 ? 'up' : 'down'}`} style={{ width }} />
            </span>
            <span className="ui-dbars__value">{item.value == null ? '–' : format(item.value)}</span>
          </div>
        );
      })}
    </div>
  );
}

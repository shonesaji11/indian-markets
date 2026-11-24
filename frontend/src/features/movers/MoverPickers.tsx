import { useState } from 'react';
import type { MoverDay } from '@/api/types';
import { Button, Popover, TextInput } from '@/components/ui';
import './movers.css';

/** "Mon 24 Nov" */
export const dayLabel = (iso: string) =>
  new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });

/** Hit rate as a whole percent, or '' with nothing to count. */
export const hitPct = (hits: number, of: number) => (of > 0 ? `${Math.round((hits / of) * 100)}%` : '');

const SHOWN = 10; // days listed in the drop-down
const TOTAL = 30; // lists in the hit-rate total

/** "After close Mon 24 Nov ▾": recent scored days with their list size and hits, the hit rate of the last lists,
 * and a date box for older days. */
export function MoverDatePicker({ value, days, onChange }: { value: string | null; days: MoverDay[]; onChange: (asOf: string) => void }) {
  const [open, setOpen] = useState(false);
  const recent = days.slice(0, SHOWN);
  const done = days.slice(0, TOTAL).filter((d) => d.next_session);
  const hits = done.reduce((s, d) => s + d.hits, 0);
  const counted = done.reduce((s, d) => s + d.with_bar, 0);
  const pick = (asOf: string) => {
    setOpen(false);
    onChange(asOf);
  };
  return (
    <Popover
      open={open}
      onClose={() => setOpen(false)}
      trigger={
        <Button aria-expanded={open} onClick={() => setOpen(!open)} title="Which day's list">
          {value ? `After close ${dayLabel(value)}` : 'Pick a day'} ▾
        </Button>
      }
    >
      <div className="mover-days">
        {recent.map((d) => (
          <button key={d.as_of} type="button" className="ui-popover__item" aria-current={d.as_of === value} onClick={() => pick(d.as_of)}>
            <span className="mover-days__day">{dayLabel(d.as_of)}</span>
            <span className="muted">
              {d.listed} · {d.next_session ? `${d.hits} hit${d.with_bar ? ` (${hitPct(d.hits, d.with_bar)})` : ''}` : 'next session'}
            </span>
          </button>
        ))}
        {done.length > 0 && (
          <div className="ui-popover__section mover-days__total muted">
            <span>Last {done.length} lists</span>
            <span>
              {hitPct(hits, counted)} hit · {hits} of {counted}
            </span>
          </div>
        )}
        <div className="ui-popover__section mover-days__older">
          <span className="muted">Older date</span>
          <TextInput type="date" value="" max={days[0]?.as_of} onChange={(e) => e.target.value && pick(e.target.value)} />
        </div>
      </div>
    </Popover>
  );
}

// From the research study's cutoff table (research/movers/ml_co_4.md).
const CUTOFFS = [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5];

/** "p ≥ 0.20 ▾": the probability a stock needs to be listed; the default is the one Telegram uses. */
export function CutoffPicker({ value, standard, onChange }: { value: number; standard: number; onChange: (v: number) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover
      open={open}
      onClose={() => setOpen(false)}
      trigger={
        <Button aria-expanded={open} onClick={() => setOpen(!open)} title="Probability a stock needs to be listed">
          p ≥ {value.toFixed(2)} ▾
        </Button>
      }
    >
      {[...new Set([...CUTOFFS, standard])].sort((a, b) => a - b).map((c) => (
        <button
          key={c}
          type="button"
          className="ui-popover__item"
          aria-current={c === value}
          onClick={() => {
            setOpen(false);
            onChange(c);
          }}
        >
          <span>p ≥ {c.toFixed(2)}</span>
          {c === standard && <span className="muted">Telegram</span>}
        </button>
      ))}
    </Popover>
  );
}

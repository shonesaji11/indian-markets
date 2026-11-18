import { useState } from 'react';
import type { HighBasis, NearHigh } from '@/api/types';
import { Button, Field, Popover, SegmentedControl, TextInput } from '@/components/ui';

const BASIS_OPTIONS = [
  { value: '52w' as const, label: '52-week' },
  { value: 'ath' as const, label: 'All-time' },
];

/** "52-week" / "all-time", for headers and subtitles. */
export const highLabel = (basis: HighBasis) => (basis === '52w' ? '52-week' : 'all-time');
/** Short form for column headers: "52w" / "all-time". */
export const highShort = (basis: HighBasis) => (basis === '52w' ? '52w' : 'all-time');

/** Button showing "52w · 10%" that drops down the near-high settings (which high, how close). */
export function NearHighPicker({ value, onChange }: { value: NearHigh; onChange: (v: NearHigh) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover
      open={open}
      onClose={() => setOpen(false)}
      align="right"
      trigger={
        <Button aria-expanded={open} onClick={() => setOpen(!open)} title="Which high, and how close counts as near">
          {value.basis === '52w' ? '52w' : 'All-time'} · {value.pct}% ▾
        </Button>
      }
    >
      <div className="near-high-picker">
        <Field label="High">
          <SegmentedControl
            value={value.basis}
            options={BASIS_OPTIONS}
            onChange={(basis) => onChange({ ...value, basis })}
            aria-label="Which high"
          />
        </Field>
        <Field label="Within %">
          <TextInput
            type="number"
            min={0.5}
            max={99}
            step={0.5}
            style={{ width: 80 }}
            value={value.pct}
            onChange={(e) => onChange({ ...value, pct: Math.min(99, Math.max(0.5, parseFloat(e.target.value) || 0.5)) })}
          />
        </Field>
        <div className="muted near-high-picker__note">
          All-time = highest since listing, or since Nov 2016 where stored history starts.
        </div>
      </div>
    </Popover>
  );
}

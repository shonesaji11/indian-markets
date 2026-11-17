import { useEffect, useRef, useState } from 'react';

interface SwatchPickerProps {
  /** Selectable colors, any CSS color (e.g. `var(--series-3)`). */
  colors: string[];
  /** Index of the current color. */
  value: number;
  /** Indexes in use elsewhere; shown with a dashed ring (still selectable). */
  taken?: number[];
  onChange: (index: number) => void;
  label?: string;
}

/** A color dot that opens a small palette. Closes on pick, Escape or a click outside. */
export function SwatchPicker({ colors, value, taken = [], onChange, label = 'Change colour' }: SwatchPickerProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <span className="ui-swatch-picker" ref={ref}>
      <button
        type="button"
        className={`ui-swatch-picker__trigger${open ? ' is-open' : ''}`}
        aria-label={label}
        aria-expanded={open}
        title={label}
        onClick={() => setOpen(!open)}
      >
        <span className="ui-swatch-picker__dot" style={{ background: colors[value] }} />
      </button>
      {open && (
        <span className="ui-swatch-picker__menu" role="listbox" aria-label={label}>
          {colors.map((color, i) => (
            <button
              key={i}
              type="button"
              role="option"
              aria-selected={i === value}
              aria-label={`Colour ${i + 1}${taken.includes(i) ? ' (in use)' : ''}`}
              className={`ui-swatch-picker__swatch${i === value ? ' is-current' : ''}${taken.includes(i) ? ' is-taken' : ''}`}
              style={{ background: color }}
              onClick={() => {
                setOpen(false);
                if (i !== value) onChange(i);
              }}
            />
          ))}
        </span>
      )}
    </span>
  );
}

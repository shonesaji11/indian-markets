import type { CSSProperties, ReactNode } from 'react';

type Tone = 'neutral' | 'success' | 'danger' | 'warn';

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={tone === 'neutral' ? 'ui-badge' : `ui-badge ui-badge--${tone}`}>{children}</span>;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="ui-empty">{children}</div>;
}

export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className="ui-error">{error instanceof Error ? error.message : String(error)}</div>;
}

export function Skeleton({ width = '100%', height = 14, style }: { width?: number | string; height?: number; style?: CSSProperties }) {
  return <div className="ui-skeleton" style={{ width, height, ...style }} aria-hidden />;
}

interface DeltaProps {
  value: number | null | undefined;
  /** Formats the absolute value; the sign/arrow is added here. */
  format: (abs: number) => string;
  arrow?: boolean;
  pill?: boolean;
}

/** A signed change. Direction is carried by sign + arrow as well as color. */
export function Delta({ value, format, arrow = false, pill = false }: DeltaProps) {
  if (value == null || Number.isNaN(value)) return <span className="ui-delta ui-delta--flat">–</span>;
  const dir = value > 0 ? 'up' : value < 0 ? 'down' : 'flat';
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  const glyph = arrow ? (dir === 'up' ? '▲ ' : dir === 'down' ? '▼ ' : '') : '';
  return (
    <span className={`ui-delta ui-delta--${dir}${pill ? ' ui-delta--pill' : ''}`}>
      {glyph}
      {sign}
      {format(Math.abs(value))}
    </span>
  );
}

interface ChipProps {
  color?: string;
  /** Replaces the static color dot, e.g. with a SwatchPicker. */
  colorControl?: ReactNode;
  onRemove?: () => void;
  children: ReactNode;
}

export function Chip({ color, colorControl, onRemove, children }: ChipProps) {
  return (
    <span className="ui-chip">
      {colorControl ?? (color && <span className="ui-chip__swatch" style={{ background: color }} />)}
      {children}
      {onRemove && (
        <button type="button" className="ui-button ui-button--ghost ui-button--sm" onClick={onRemove} aria-label="Remove">
          ×
        </button>
      )}
    </span>
  );
}

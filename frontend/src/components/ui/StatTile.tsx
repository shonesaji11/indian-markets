import type { ReactNode } from 'react';

interface StatTileProps {
  label: ReactNode;
  value: ReactNode;
  /** Usually a <Delta>; sits under the value. */
  delta?: ReactNode;
  /** Secondary text next to the delta. */
  note?: ReactNode;
  /** Optional visual under the figures, e.g. a <Sparkline>. */
  children?: ReactNode;
  onClick?: () => void;
  title?: string;
}

/** A headline number with its change: value first, then delta, then optional context. */
export function StatTile({ label, value, delta, note, children, onClick, title }: StatTileProps) {
  return (
    <div
      className={onClick ? 'ui-stat ui-stat--clickable' : 'ui-stat'}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => (e.key === 'Enter' || e.key === ' ') && onClick() : undefined}
      title={title}
    >
      <div className="ui-stat__label">{label}</div>
      <div className="ui-stat__value">{value}</div>
      {(delta || note) && (
        <div className="ui-stat__foot">
          {delta}
          {note && <span className="muted">{note}</span>}
        </div>
      )}
      {children && <div className="ui-stat__extra">{children}</div>}
    </div>
  );
}

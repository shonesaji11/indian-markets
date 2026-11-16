import type { ReactNode } from 'react';

interface CardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /** Remove body padding, e.g. for tables and charts that should run edge to edge. */
  flush?: boolean;
  /** Draw a rule under the header (useful above tables). */
  divided?: boolean;
  className?: string;
  children: ReactNode;
}

export function Card({ title, subtitle, actions, flush, divided, className, children }: CardProps) {
  return (
    <section className={['ui-card', className].filter(Boolean).join(' ')}>
      {(title || actions) && (
        <header className={divided ? 'ui-card__header ui-card__header--divided' : 'ui-card__header'}>
          <div style={{ minWidth: 0 }}>
            {title && <h2 className="ui-card__title">{title}</h2>}
            {subtitle && <div className="ui-card__subtitle">{subtitle}</div>}
          </div>
          {actions && <div className="ui-row">{actions}</div>}
        </header>
      )}
      <div className={flush ? 'ui-card__body ui-card__body--flush' : 'ui-card__body'}>{children}</div>
    </section>
  );
}

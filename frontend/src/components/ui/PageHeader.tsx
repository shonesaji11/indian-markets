import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="ui-page-header">
      <div>
        <h1 className="ui-page-header__title">{title}</h1>
        {subtitle && <div className="ui-page-header__subtitle">{subtitle}</div>}
      </div>
      {actions && <div className="ui-row">{actions}</div>}
    </div>
  );
}

import type { ButtonHTMLAttributes } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'ghost';
  size?: 'md' | 'sm';
  /** Square button sized for a single icon/glyph. */
  icon?: boolean;
  loading?: boolean;
}

export function Button({ variant = 'default', size = 'md', icon, loading, disabled, className, children, ...rest }: ButtonProps) {
  const classes = [
    'ui-button',
    variant !== 'default' && `ui-button--${variant}`,
    size === 'sm' && 'ui-button--sm',
    icon && 'ui-button--icon',
    className,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button type="button" className={classes} disabled={disabled || loading} aria-busy={loading} {...rest}>
      {loading && <span className="ui-spinner" aria-hidden />}
      {children}
    </button>
  );
}

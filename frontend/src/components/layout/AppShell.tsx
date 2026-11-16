import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { SegmentedControl } from '@/components/ui';
import { useThemePreference, type ThemePreference } from '@/hooks/useTheme';
import './layout.css';

export interface NavItem {
  to: string;
  label: string;
  end?: boolean;
}

const THEMES = [
  { value: 'system', label: 'Auto' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
] as const satisfies readonly { value: ThemePreference; label: string }[];

export function AppShell({ title, nav, children }: { title: string; nav: NavItem[]; children: ReactNode }) {
  const [theme, setTheme] = useThemePreference();
  return (
    <div className="shell">
      <header className="shell__header">
        <div className="shell__brand">
          <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden>
            <rect width="20" height="20" rx="5" fill="var(--accent)" />
            <path d="M4 13.5l3.5-4 3 2.5L16 6" stroke="#fff" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>{title}</span>
        </div>
        <nav className="shell__nav">
          {nav.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => (isActive ? 'active' : undefined)}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="shell__tools">
          <SegmentedControl value={theme} options={THEMES} onChange={setTheme} aria-label="Theme" />
        </div>
      </header>
      <main className="shell__main">{children}</main>
    </div>
  );
}

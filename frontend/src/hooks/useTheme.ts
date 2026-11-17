import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { loadSetting, saveSetting } from '@/lib/storage';

export type ThemePreference = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'markets.theme';
const media = window.matchMedia('(prefers-color-scheme: light)');

function readPreference(): ThemePreference {
  const value = loadSetting(STORAGE_KEY);
  return value === 'light' || value === 'dark' ? value : 'system';
}

function apply(pref: ThemePreference) {
  if (pref === 'system') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', pref);
}

// --- a tiny store so every chart re-reads CSS variables when the theme changes ---
let version = 0;
const listeners = new Set<() => void>();
function bump() {
  version += 1;
  listeners.forEach((l) => l());
}
media.addEventListener('change', bump);

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Changes whenever the effective theme may have changed; use it as an effect dependency. */
export function useThemeVersion(): number {
  return useSyncExternalStore(subscribe, () => version);
}

export function useThemePreference(): [ThemePreference, (pref: ThemePreference) => void] {
  const [pref, setPref] = useState<ThemePreference>(readPreference);

  useEffect(() => apply(pref), [pref]);

  const update = useCallback((next: ThemePreference) => {
    saveSetting(STORAGE_KEY, next === 'system' ? null : next);
    apply(next);
    setPref(next);
    bump();
  }, []);

  return [pref, update];
}

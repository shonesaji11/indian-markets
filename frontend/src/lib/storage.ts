/**
 * Per-browser preferences in localStorage. Storage can be unavailable (private mode, blocked site
 * data), so reads fall back to null and failed writes are ignored: the setting then lasts only
 * for the session.
 */
export function loadSetting(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** `null` removes the setting. */
export function saveSetting(key: string, value: string | null): void {
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // not persisted
  }
}

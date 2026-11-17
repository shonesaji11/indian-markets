/**
 * Per-browser preferences in localStorage (or per-tab values in sessionStorage with `session`). Storage can be unavailable (private mode, blocked site
 * data), so reads fall back to null and failed writes are ignored: the setting then lasts only
 * for the session.
 */
export function loadSetting(key: string, session = false): string | null {
  try {
    return (session ? sessionStorage : localStorage).getItem(key);
  } catch {
    return null;
  }
}

/** `null` removes the setting. */
export function saveSetting(key: string, value: string | null, session = false): void {
  try {
    const store = session ? sessionStorage : localStorage;
    if (value == null) store.removeItem(key);
    else store.setItem(key, value);
  } catch {
    // not persisted
  }
}

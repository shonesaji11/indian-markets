import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

/** Converts a value to and from its query-string form. Keep codecs at module level (stable identity). */
export interface UrlCodec<T> {
  parse: (raw: string) => T;
  format: (value: T) => string;
}

const stringCodec: UrlCodec<string> = { parse: (raw) => raw, format: (value) => value };

export const boolCodec: UrlCodec<boolean> = { parse: (raw) => raw === '1', format: (value) => (value ? '1' : '0') };

export const intCodec: UrlCodec<number> = { parse: (raw) => parseInt(raw, 10) || 0, format: (value) => String(value) };

/** Decimal numbers (e.g. 7.5); unparseable = 0. */
export const numberCodec: UrlCodec<number> = { parse: (raw) => parseFloat(raw) || 0, format: (value) => String(value) };

/** `10,20` <-> [10, 20]; non-numbers are dropped. */
export const intListCodec: UrlCodec<number[]> = {
  parse: (raw) => raw.split(',').map((v) => parseInt(v, 10)).filter((v) => v > 0),
  format: (value) => value.join(','),
};

/**
 * useState backed by a query parameter, so the value survives Back, reload and shared links.
 * Updates replace the current history entry (changing a filter doesn't add a Back step), and a
 * value equal to the fallback is removed from the URL to keep links short.
 */
export function useUrlState(key: string, fallback?: string): [string, (value: string) => void];
export function useUrlState<T>(key: string, fallback: T, codec: UrlCodec<T>): [T, (value: T) => void];
export function useUrlState<T>(key: string, fallback: T, codec?: UrlCodec<T>): [T, (value: T) => void] {
  const c = codec ?? (stringCodec as unknown as UrlCodec<T>);
  const fb = fallback ?? ('' as T);
  const [search, setSearch] = useSearchParams();
  const raw = search.get(key);
  // Parse only when the raw string changes, so arrays/objects keep their identity between renders.
  const value = useMemo(() => (raw == null ? fb : c.parse(raw)), [raw]);

  const setValue = useCallback(
    (next: T) =>
      setSearch(
        (prev) => {
          const params = new URLSearchParams(prev);
          const formatted = c.format(next);
          if (formatted === c.format(fb)) params.delete(key);
          else params.set(key, formatted);
          return params;
        },
        { replace: true },
      ),
    [key, setSearch],
  );

  return [value, setValue];
}

/**
 * Set several query params in one history update (separate useUrlState setters called in the same
 * event would overwrite each other). Pass formatted strings; undefined removes the param.
 */
export function useUrlUpdate(): (patch: Record<string, string | undefined>) => void {
  const [, setSearch] = useSearchParams();
  return useCallback(
    (patch) =>
      setSearch(
        (prev) => {
          const params = new URLSearchParams(prev);
          for (const [key, value] of Object.entries(patch)) {
            if (value === undefined) params.delete(key);
            else params.set(key, value);
          }
          return params;
        },
        { replace: true },
      ),
    [setSearch],
  );
}

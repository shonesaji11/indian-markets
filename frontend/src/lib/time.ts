import type { UTCTimestamp } from 'lightweight-charts';

/**
 * Backend timestamps are naive IST ("2024-01-02T09:15:00"). Charts work in UTC seconds,
 * so we read the wall-clock time as if it were UTC: the axis then shows IST times as-is.
 */
export function toChartTime(ts: string): UTCTimestamp {
  const hasZone = /([zZ]|[+-]\d\d:\d\d)$/.test(ts);
  return Math.floor(Date.parse(hasZone ? ts : `${ts}Z`) / 1000) as UTCTimestamp;
}

export function formatDate(ts: string | null | undefined): string {
  return ts ? ts.slice(0, 10) : '';
}

export function formatDateTime(ts: string | null | undefined): string {
  return ts ? ts.slice(0, 19).replace('T', ' ') : '';
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

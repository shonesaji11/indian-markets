const price = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat('en-IN');

export const fmt = {
  price: (v: number | null | undefined) => (v == null ? '' : price.format(v)),
  compact: (v: number | null | undefined) => (v == null ? '' : compact.format(v)),
  int: (v: number | null | undefined) => (v == null ? '' : integer.format(v)),
  pct: (v: number | null | undefined) => (v == null ? '' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`),
  /** Unsigned percentage, for use inside <Delta> which adds the sign. */
  pctAbs: (v: number) => `${(v * 100).toFixed(2)}%`,
  shortDate: (iso: string | null | undefined) =>
    iso ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '',
  longDate: (iso: string | null | undefined) =>
    iso
      ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-IN', {
          weekday: 'short',
          day: 'numeric',
          month: 'short',
          year: 'numeric',
        })
      : '',
  ratio: (v: number | null | undefined) => (v == null ? '' : `${v.toFixed(2)}×`),
};

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

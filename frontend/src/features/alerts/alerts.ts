import type { AlertDirection, PriceAlert } from '@/api/types';
import { fmt } from '@/lib/format';

export const DIRECTIONS: { value: AlertDirection; label: string }[] = [
  { value: 'above', label: 'Above' },
  { value: 'below', label: 'Below' },
];

export const alertLabel = (a: { direction: AlertDirection; price: number }) =>
  `${a.direction === 'above' ? 'Above' : 'Below'} ${fmt.price(a.price)}`;

/** The level counts when reached or jumped over (same rule as the backend's `is_hit`). */
export const isMet = (direction: AlertDirection, level: number, price: number) =>
  direction === 'above' ? price >= level : price <= level;

/** Active (not yet fired) alerts by stock, oldest first. */
export function activeByInstrument(alerts: PriceAlert[] | undefined): Map<number, PriceAlert[]> {
  const out = new Map<number, PriceAlert[]>();
  for (const a of alerts ?? []) {
    if (!a.triggered_at) out.set(a.instrument_id, [...(out.get(a.instrument_id) ?? []), a]);
  }
  return out;
}

/** How far the level is from the price, as a fraction (null without a price). */
export const away = (level: number, now: number | null | undefined) => (now ? Math.abs(level / now - 1) : null);

/** A typed price ("2,980", "2980.5") as a number; null unless it's a number above 0. */
export function parsePrice(text: string): number | null {
  const value = Number(text.replace(/[,\s₹]/g, ''));
  return text.trim() !== '' && Number.isFinite(value) && value > 0 ? value : null;
}

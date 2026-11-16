import type { ParamValue } from '@/api/types';
import type { UrlCodec } from '@/hooks/useUrlState';
import type { IndicatorSelection } from './IndicatorPicker';
import { SERIES_SLOTS } from './toChartSeries';

export interface ActiveIndicator extends IndicatorSelection {
  /** Categorical color slot, 1..8 (--series-N). Unique within a list, so it doubles as the key. */
  slot: number;
}

/** Append a selection using the first free color slot. */
export function addIndicator(list: ActiveIndicator[], sel: IndicatorSelection): ActiveIndicator[] {
  const used = new Set(list.map((i) => i.slot));
  const slot = Array.from({ length: SERIES_SLOTS }, (_, n) => n + 1).find((s) => !used.has(s)) ?? 1;
  return [...list, { ...sel, slot }];
}

function parseValue(raw: string): ParamValue {
  if (raw === 'true' || raw === 'false') return raw === 'true';
  return raw !== '' && !Number.isNaN(Number(raw)) ? Number(raw) : raw;
}

/** `sma:2:period=50,source=close;rsi:3:period=14` <-> ActiveIndicator[] (empty string = none). */
export const indicatorsCodec: UrlCodec<ActiveIndicator[]> = {
  format: (list) =>
    list
      .map((i) => `${i.name}:${i.slot}:${Object.entries(i.params).map(([k, v]) => `${k}=${v}`).join(',')}`)
      .join(';'),
  parse: (raw) =>
    raw
      .split(';')
      .filter(Boolean)
      .map((part) => {
        const [name, slot, params = ''] = part.split(':');
        const entries = params
          .split(',')
          .filter(Boolean)
          .map((kv) => {
            const [k, v = ''] = kv.split('=');
            return [k, parseValue(v)] as const;
          });
        return { name, slot: Number(slot) || 1, params: Object.fromEntries(entries) };
      }),
};

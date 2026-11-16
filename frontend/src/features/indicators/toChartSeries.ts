import type { CalcSeries } from '@/api/types';
import type { ChartSeries, ValuePoint } from '@/components/charts';
import { toChartTime } from '@/lib/time';

/** Indicators drawn on the price scale; everything else gets its own pane. */
const PRICE_OVERLAYS = new Set(['sma', 'ema', 'bollinger']);
/** Outputs better shown as bars. */
const HISTOGRAM_OUTPUTS = new Set(['histogram']);

/** Number of categorical series slots (--series-1 .. --series-8). */
export const SERIES_SLOTS = 8;

export function isOverlay(name: string): boolean {
  return PRICE_OVERLAYS.has(name);
}

export function paramsLabel(params: Record<string, unknown>): string {
  return Object.values(params).join(',');
}

/**
 * Convert one stored calculation into chart series (one per output). Output i uses the
 * slot after the indicator's own, so multi-line indicators stay distinguishable.
 */
export function toChartSeries(calc: CalcSeries, slot: number, pane: number, colorOf: (slot: number) => string): ChartSeries[] {
  return calc.outputs.map((output, i) => {
    const data: ValuePoint[] = [];
    for (const p of calc.points) {
      const v = p[output];
      if (typeof v === 'number') data.push({ time: toChartTime(p.ts), value: v });
    }
    return {
      id: `${calc.calc_id}:${output}`,
      kind: HISTOGRAM_OUTPUTS.has(output) ? 'histogram' : 'line',
      data,
      color: colorOf(((slot - 1 + i) % SERIES_SLOTS) + 1),
      pane,
      label: i === 0 ? `${calc.name}(${paramsLabel(calc.params)})` : output,
    } satisfies ChartSeries;
  });
}

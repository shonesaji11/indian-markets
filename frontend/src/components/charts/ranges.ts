import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  Logical,
  SeriesAttachedParameter,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';
import { fmt } from '@/lib/format';

/** Price range measures the move between two points; date range measures the time between them. */
export type RangeKind = 'price' | 'date';

export interface RangePoint {
  time: UTCTimestamp;
  price: number;
}

export interface MeasuredRange {
  kind: RangeKind;
  from: RangePoint;
  to: RangePoint;
}

export interface RangeTheme {
  up: string;
  down: string;
  accent: string;
  font: string;
}

type Target = Parameters<IPrimitivePaneRenderer['draw']>[0];

/** Index of the last bar at or before `time` (times sorted ascending); 0 if before the first. */
export function barIndex(times: readonly number[], time: number): number {
  let lo = 0;
  let hi = times.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (times[mid] <= time) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/** Calendar time between two chart timestamps: '15 days' for whole days, else '1d 3h 15m'. */
function duration(seconds: number): string {
  if (seconds % 86400 === 0) {
    const days = seconds / 86400;
    return `${days} ${days === 1 ? 'day' : 'days'}`;
  }
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return [d && `${d}d`, h && `${h}h`, `${m}m`].filter(Boolean).join(' ');
}

/** The label drawn on a range, e.g. '+34.00 (+15.90%) · 8 bars' or '11 bars · 15 days'. */
export function rangeLabel(range: MeasuredRange, times: readonly number[]): string {
  const n = Math.abs(barIndex(times, range.to.time) - barIndex(times, range.from.time));
  const bars = `${n} ${n === 1 ? 'bar' : 'bars'}`;
  if (range.kind === 'date') return `${bars} · ${duration(Math.abs(range.to.time - range.from.time))}`;
  const change = range.to.price - range.from.price;
  const pct = range.from.price > 0 ? ` (${fmt.pct(change / range.from.price)})` : '';
  return `${change >= 0 ? '+' : ''}${fmt.price(change)}${pct} · ${bars}`;
}

/**
 * Draws price/date range boxes on a candle series. Ranges are pinned to bar times and prices, so they
 * pan and zoom with the chart. Points snap to the bar at or before their time.
 */
export class RangesPrimitive implements ISeriesPrimitive<Time> {
  private ranges: readonly MeasuredRange[] = [];
  private draft: MeasuredRange | null = null;
  private times: readonly number[] = [];
  private theme: RangeTheme = {
    up: '#22b24c',
    down: '#e66767',
    accent: '#3987e5',
    font: 'sans-serif',
  };
  private chart: IChartApi | null = null;
  private series: ISeriesApi<'Candlestick'> | null = null;
  private requestUpdate: () => void = () => {};
  private readonly views: IPrimitivePaneView[] = [{ renderer: () => ({ draw: (t) => this.draw(t) }) }];

  attached({ chart, series, requestUpdate }: SeriesAttachedParameter<Time>) {
    this.chart = chart as IChartApi;
    this.series = series as ISeriesApi<'Candlestick'>;
    this.requestUpdate = requestUpdate;
  }

  detached() {
    this.chart = null;
    this.series = null;
    this.requestUpdate = () => {};
  }

  paneViews() {
    return this.views;
  }

  setRanges(ranges: readonly MeasuredRange[]) {
    this.ranges = ranges;
    this.requestUpdate();
  }

  setDraft(draft: MeasuredRange | null) {
    this.draft = draft;
    this.requestUpdate();
  }

  setTimes(times: readonly number[]) {
    this.times = times;
    this.requestUpdate();
  }

  setTheme(theme: RangeTheme) {
    this.theme = theme;
    this.requestUpdate();
  }

  /** Chart point under a pixel position, snapped to a bar; null off the data or price scale. */
  pointAt(x: number, y: number): RangePoint | null {
    const pane = this.chart?.panes()[0];
    if (!this.chart || !pane || x < 0 || y < 0 || x > this.chart.timeScale().width() || y > pane.getHeight()) return null;
    const logical = this.chart?.timeScale().coordinateToLogical(x);
    const price = this.series?.coordinateToPrice(y);
    if (logical == null || price == null || this.times.length === 0) return null;
    const i = Math.min(Math.max(Math.round(logical), 0), this.times.length - 1);
    return { time: this.times[i] as UTCTimestamp, price };
  }

  private draw(target: Target) {
    const all = this.draft ? [...this.ranges, this.draft] : this.ranges;
    if (!this.chart || !this.series || all.length === 0 || this.times.length === 0) return;
    const scale = this.chart.timeScale();
    const series = this.series;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.font = `11px ${this.theme.font}`;
      ctx.textBaseline = 'middle';
      for (const range of all) {
        const x1 = scale.logicalToCoordinate(barIndex(this.times, range.from.time) as Logical);
        const x2 = scale.logicalToCoordinate(barIndex(this.times, range.to.time) as Logical);
        const y1 = series.priceToCoordinate(range.from.price);
        const y2 = series.priceToCoordinate(range.to.price);
        if (x1 == null || x2 == null || y1 == null || y2 == null) continue;
        const color =
          range.kind === 'date'
            ? this.theme.accent
            : range.to.price >= range.from.price
              ? this.theme.up
              : this.theme.down;
        const left = Math.min(x1, x2);
        const top = Math.min(y1, y2);
        const w = Math.abs(x2 - x1);
        const h = Math.abs(y2 - y1);

        ctx.fillStyle = color;
        ctx.globalAlpha = 0.15;
        ctx.fillRect(left, top, w, h);
        ctx.globalAlpha = 1;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.setLineDash(range === this.draft ? [4, 3] : []);
        ctx.strokeRect(left, top, w, h);
        ctx.setLineDash([]);

        // Arrow from the first point towards the second, through the middle of the box.
        const [ax1, ay1, ax2, ay2] =
          range.kind === 'price' ? [left + w / 2, y1, left + w / 2, y2] : [x1, top + h / 2, x2, top + h / 2];
        const angle = Math.atan2(ay2 - ay1, ax2 - ax1);
        ctx.beginPath();
        ctx.moveTo(ax1, ay1);
        ctx.lineTo(ax2, ay2);
        if (Math.hypot(ax2 - ax1, ay2 - ay1) > 8) {
          ctx.moveTo(ax2 - 6 * Math.cos(angle - 0.5), ay2 - 6 * Math.sin(angle - 0.5));
          ctx.lineTo(ax2, ay2);
          ctx.lineTo(ax2 - 6 * Math.cos(angle + 0.5), ay2 - 6 * Math.sin(angle + 0.5));
        }
        ctx.stroke();

        // Label: above the box for price ranges, below for date ranges; flipped when it would leave the pane.
        const text = rangeLabel(range, this.times);
        const lw = ctx.measureText(text).width + 12;
        const lh = 18;
        const above = top - lh - 4;
        const below = top + h + 4;
        let ly = range.kind === 'price' ? above : below;
        if (ly < 0) ly = below;
        if (ly + lh > mediaSize.height) ly = Math.max(0, above);
        const lx = Math.min(Math.max(left + w / 2 - lw / 2, 2), mediaSize.width - lw - 2);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.roundRect(lx, ly, lw, lh, 3);
        ctx.fill();
        ctx.fillStyle = '#fff';
        ctx.fillText(text, lx + 6, ly + lh / 2);
      }
    });
  }
}

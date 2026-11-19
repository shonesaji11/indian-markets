import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useThemeVersion } from '@/hooks/useTheme';
import { cssVar } from '@/lib/format';
import { toChartTime } from '@/lib/time';
import { ChartLegend, type LegendItem } from './ChartLegend';
import { applyChartTheme, baseLayout } from './theme';
import { RangesPrimitive, type MeasuredRange, type RangeKind } from './ranges';

export interface OhlcPoint {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface ValuePoint {
  time: UTCTimestamp;
  value: number;
  color?: string;
}

export interface ChartSeries {
  id: string;
  kind: 'line' | 'histogram';
  data: ValuePoint[];
  color: string;
  /** 0 = on top of price; 1, 2, ... = separate panes below. */
  pane?: number;
  label?: string;
  /** Series sharing a group (one indicator's outputs) form one legend row, labelled by the first. */
  group?: string;
}

/** API candles (ISO `ts`) -> chart points. */
export function toOhlc(rows: { ts: string; open: number; high: number; low: number; close: number }[]): OhlcPoint[] {
  return rows.map((c) => ({ time: toChartTime(c.ts), open: c.open, high: c.high, low: c.low, close: c.close }));
}

interface PriceChartProps {
  candles: OhlcPoint[];
  volume?: ValuePoint[];
  series?: ChartSeries[];
  /** Pixels, or any CSS height (e.g. one based on the window). */
  height?: number | string;
  showTime?: boolean;
  /**
   * Miniature: candles only, static (no scroll, zoom or crosshair), no axes, last-price marker or
   * TradingView logo. For grids of small charts; the grid must credit TradingView once instead.
   */
  compact?: boolean;
  /** Price/date ranges to draw (ignored when compact). */
  ranges?: readonly MeasuredRange[];
  /** While set, two clicks on the chart measure a range of this kind and pass it to `onRangeAdd`. */
  rangeTool?: RangeKind | null;
  onRangeAdd?: (range: MeasuredRange) => void;
  /** The forming bar from live prices (same time as the last candle, or later), drawn in a lighter shade. */
  live?: { bar: OhlcPoint; volume?: ValuePoint } | null;
}

/** Candlestick chart with optional volume and any number of extra line/histogram series. */
export function PriceChart({
  candles,
  volume,
  series = [],
  height = 520,
  showTime = false,
  compact = false,
  ranges = [],
  rangeTool = null,
  onRangeAdd,
  live = null,
}: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const rangesRef = useRef<RangesPrimitive | null>(null);
  const onRangeAddRef = useRef(onRangeAdd);
  onRangeAddRef.current = onRangeAdd;
  const themeVersion = useThemeVersion();
  /** Series values at the crosshair bar, by series id; null = mouse off the chart, show the latest. */
  const [hover, setHover] = useState<Map<string, number | undefined> | null>(null);

  // Create the chart once.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: baseLayout(!compact),
      crosshair: { mode: 0 },
      // Empty space after the last bar, as on TradingView; also kept by a time-axis double-click.
      timeScale: { rightOffset: 10 },
      ...(compact && {
        handleScroll: false,
        handleScale: false,
        crosshair: { vertLine: { visible: false }, horzLine: { visible: false } },
        timeScale: { visible: false },
        rightPriceScale: { visible: false },
      }),
    });
    candleRef.current = chart.addSeries(CandlestickSeries, {
      borderVisible: false,
      ...(compact && { lastValueVisible: false, priceLineVisible: false }),
    });
    const vol = chart.addSeries(HistogramSeries, { priceScaleId: '', priceFormat: { type: 'volume' }, lastValueVisible: false });
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volumeRef.current = vol;
    if (!compact) {
      rangesRef.current = new RangesPrimitive();
      candleRef.current.attachPrimitive(rangesRef.current);
    }
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      rangesRef.current = null;
    };
  }, [compact]);

  // Colors come from CSS tokens; re-read them whenever the theme changes.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    applyChartTheme(chart);
    const up = cssVar('--up');
    const down = cssVar('--down');
    candleRef.current?.applyOptions({ upColor: up, downColor: down, wickUpColor: up, wickDownColor: down });
    rangesRef.current?.setTheme({ up, down, accent: cssVar('--accent'), font: cssVar('--font') });
  }, [themeVersion]);

  useEffect(() => {
    chartRef.current?.applyOptions({ timeScale: { timeVisible: showTime } });
  }, [showTime]);

  useEffect(() => {
    candleRef.current?.setData(candles);
    rangesRef.current?.setTimes(candles.map((c) => c.time));
    // Miniatures show all their bars; the full chart opens at the default zoom on the latest bars, as a
    // double-click on the time axis does (fitting years of daily bars squeezes candles to slivers).
    const scale = chartRef.current?.timeScale();
    if (compact) scale?.fitContent();
    else scale?.resetTimeScale();
  }, [candles, compact]);

  useEffect(() => {
    rangesRef.current?.setRanges(ranges);
  }, [ranges]);

  // Measuring: first click fixes the start, the box follows the crosshair, second click finishes. Esc cancels.
  useEffect(() => {
    const chart = chartRef.current;
    const prim = rangesRef.current;
    const el = containerRef.current;
    if (!rangeTool || !chart || !prim || !el) return;
    let draft: MeasuredRange | null = null;
    // Own click detection: the chart's click event drops a second click within 500 ms (double-click check).
    let down: { x: number; y: number } | null = null;
    const onDown = (e: PointerEvent) => {
      down = { x: e.clientX, y: e.clientY };
    };
    const onUp = (e: PointerEvent) => {
      if (!down || Math.abs(e.clientX - down.x) + Math.abs(e.clientY - down.y) > 5) return; // a drag (pan)
      down = null;
      const rect = el.getBoundingClientRect();
      const point = prim.pointAt(e.clientX - rect.left, e.clientY - rect.top);
      if (!point) return;
      if (!draft) {
        draft = { kind: rangeTool, from: point, to: point };
        prim.setDraft(draft);
        return;
      }
      const done = { ...draft, to: point };
      draft = null;
      prim.setDraft(null);
      onRangeAddRef.current?.(done);
    };
    const onMove = (p: MouseEventParams<Time>) => {
      const point = draft && p.point && prim.pointAt(p.point.x, p.point.y);
      if (!draft || !point) return;
      draft = { ...draft, to: point };
      prim.setDraft(draft);
    };
    // Capture phase, so the page's own Esc handler can see the draft was cancelled (defaultPrevented).
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || !draft) return;
      draft = null;
      prim.setDraft(null);
      e.preventDefault();
    };
    el.addEventListener('pointerdown', onDown);
    el.addEventListener('pointerup', onUp);
    chart.subscribeCrosshairMove(onMove);
    window.addEventListener('keydown', onKey, true);
    el.style.cursor = 'crosshair';
    return () => {
      el.style.cursor = '';
      el.removeEventListener('pointerdown', onDown);
      el.removeEventListener('pointerup', onUp);
      window.removeEventListener('keydown', onKey, true);
      if (chartRef.current !== chart) return; // chart already disposed
      chart.unsubscribeCrosshairMove(onMove);
      prim.setDraft(null);
    };
  }, [rangeTool]);

  useEffect(() => {
    volumeRef.current?.setData(volume ?? []);
  }, [volume]);

  // Live: the forming bar in a lighter shade. When a new slot starts, the bar it replaces is finished and is
  // redrawn in normal colours (the chart can only update its last bar). New stored candles start afresh.
  const finished = useRef<OhlcPoint[]>([]);
  const forming = useRef<OhlcPoint | null>(null);
  useEffect(() => {
    finished.current = [];
    forming.current = null;
  }, [candles]);
  useEffect(() => {
    const candleSeries = candleRef.current;
    if (!candleSeries || !live) return;
    const prev = forming.current;
    if (prev && prev.time !== live.bar.time) {
      finished.current.push(prev);
      candleSeries.setData([...candles, ...finished.current]);
    }
    forming.current = live.bar;
    const color = `${cssVar(live.bar.close >= live.bar.open ? '--up' : '--down')}99`;
    try {
      candleSeries.update({ ...live.bar, color, wickColor: color });
      if (live.volume) volumeRef.current?.update(live.volume);
    } catch {
      // older than the chart's last bar (shouldn't happen: nextLiveBar never goes back); skip this one
    }
  }, [live, candles, themeVersion]);

  // Extra series are recreated whenever the list changes; cheap at these sizes.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const created = series.map((s) => {
      // No title: names and values go in the legend instead of a tag over the candles.
      const options = { color: s.color, lastValueVisible: false, priceLineVisible: false };
      const api =
        s.kind === 'line'
          ? chart.addSeries(LineSeries, { ...options, lineWidth: 2 }, s.pane ?? 0)
          : chart.addSeries(HistogramSeries, options, s.pane ?? 0);
      api.setData(s.data);
      return api;
    });
    const onMove = (p: MouseEventParams<Time>) => {
      if (p.time === undefined) return setHover(null);
      const at = (i: number) => (p.seriesData.get(created[i]) as { value?: number } | undefined)?.value;
      setHover(new Map(series.map((s, i) => [s.id, at(i)])));
    };
    if (!compact) chart.subscribeCrosshairMove(onMove);
    setHover(null);
    return () => {
      if (chartRef.current !== chart) return; // chart already disposed
      chart.unsubscribeCrosshairMove(onMove);
      created.forEach((api) => chart.removeSeries(api));
      const panes = chart.panes();
      for (let i = panes.length - 1; i > 0; i--) {
        if (panes[i].getSeries().length === 0) chart.removePane(i);
      }
    };
  }, [series, compact]);

  const legend = useMemo(() => {
    const items = new Map<string, LegendItem>();
    for (const s of series) {
      const value = hover ? hover.get(s.id) : s.data[s.data.length - 1]?.value;
      const key = s.group ?? s.id;
      const item = items.get(key);
      if (item) item.values.push(value);
      else items.set(key, { key, label: s.label ?? s.id, color: s.color, values: [value] });
    }
    return [...items.values()];
  }, [series, hover]);

  return (
    <div style={{ position: 'relative', height, width: '100%' }}>
      <div ref={containerRef} style={{ height: '100%', width: '100%' }} />
      {!compact && <ChartLegend items={legend} />}
    </div>
  );
}

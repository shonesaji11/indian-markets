import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import { useEffect, useRef } from 'react';
import { useThemeVersion } from '@/hooks/useTheme';
import { cssVar } from '@/lib/format';
import { toChartTime } from '@/lib/time';

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
}

/** API candles (ISO `ts`) -> chart points. */
export function toOhlc(rows: { ts: string; open: number; high: number; low: number; close: number }[]): OhlcPoint[] {
  return rows.map((c) => ({ time: toChartTime(c.ts), open: c.open, high: c.high, low: c.low, close: c.close }));
}

interface PriceChartProps {
  candles: OhlcPoint[];
  volume?: ValuePoint[];
  series?: ChartSeries[];
  height?: number;
  showTime?: boolean;
  /**
   * Miniature: candles only, static (no scroll, zoom or crosshair), no axes, last-price marker or
   * TradingView logo. For grids of small charts; the grid must credit TradingView once instead.
   */
  compact?: boolean;
}

/** Candlestick chart with optional volume and any number of extra line/histogram series. */
export function PriceChart({ candles, volume, series = [], height = 520, showTime = false, compact = false }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const themeVersion = useThemeVersion();

  // Create the chart once.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        fontSize: 11,
        fontFamily: cssVar('--font'),
        attributionLogo: !compact,
      },
      crosshair: { mode: 0 },
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
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [compact]);

  // Colors come from CSS tokens; re-read them whenever the theme changes.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const grid = cssVar('--grid');
    const axis = cssVar('--axis');
    chart.applyOptions({
      layout: { textColor: cssVar('--text-muted') },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderColor: axis },
      timeScale: { borderColor: axis },
    });
    const up = cssVar('--up');
    const down = cssVar('--down');
    candleRef.current?.applyOptions({ upColor: up, downColor: down, wickUpColor: up, wickDownColor: down });
  }, [themeVersion]);

  useEffect(() => {
    chartRef.current?.applyOptions({ timeScale: { timeVisible: showTime } });
  }, [showTime]);

  useEffect(() => {
    candleRef.current?.setData(candles);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  useEffect(() => {
    volumeRef.current?.setData(volume ?? []);
  }, [volume]);

  // Extra series are recreated whenever the list changes; cheap at these sizes.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const created = series.map((s) => {
      const options = { color: s.color, title: s.label ?? '', lastValueVisible: false, priceLineVisible: false };
      const api =
        s.kind === 'line'
          ? chart.addSeries(LineSeries, { ...options, lineWidth: 2 }, s.pane ?? 0)
          : chart.addSeries(HistogramSeries, options, s.pane ?? 0);
      api.setData(s.data);
      return api;
    });
    return () => {
      if (chartRef.current !== chart) return; // chart already disposed
      created.forEach((api) => chart.removeSeries(api));
      const panes = chart.panes();
      for (let i = panes.length - 1; i > 0; i--) {
        if (panes[i].getSeries().length === 0) chart.removePane(i);
      }
    };
  }, [series]);

  return <div ref={containerRef} style={{ height, width: '100%' }} />;
}

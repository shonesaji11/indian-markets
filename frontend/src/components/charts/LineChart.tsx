import { LineSeries, createChart, type IChartApi } from 'lightweight-charts';
import { useEffect, useRef } from 'react';
import { useThemeVersion } from '@/hooks/useTheme';
import type { ValuePoint } from './PriceChart';
import { applyChartTheme, baseLayout } from './theme';

export interface LineSpec {
  id: string;
  label: string;
  /** CSS colour value (resolved, not a var()). */
  color: string;
  data: ValuePoint[];
}

interface LineChartProps {
  lines: LineSpec[];
  height?: number;
  /** Price-axis and crosshair label for a value. */
  format?: (v: number) => string;
}

/** Plain multi-line time chart (e.g. comparing return paths); fits all points, no scrolling. */
export function LineChart({ lines, height = 200, format = (v) => v.toFixed(2) }: LineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const formatRef = useRef(format);
  formatRef.current = format;
  const themeVersion = useThemeVersion();

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: baseLayout(),
      crosshair: { mode: 0 },
      handleScroll: false,
      handleScale: false,
      localization: { priceFormatter: (v: number) => formatRef.current(v) },
    });
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (chartRef.current) applyChartTheme(chartRef.current);
  }, [themeVersion]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const created = lines.map((l) => {
      const api = chart.addSeries(LineSeries, {
        color: l.color,
        lineWidth: 2,
        priceLineVisible: false,
        title: l.label,
      });
      api.setData(l.data);
      return api;
    });
    chart.timeScale().fitContent();
    return () => {
      if (chartRef.current === chart) created.forEach((api) => chart.removeSeries(api));
    };
  }, [lines]);

  return <div ref={containerRef} style={{ height, width: '100%' }} />;
}

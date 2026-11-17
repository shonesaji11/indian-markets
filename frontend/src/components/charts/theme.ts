import { ColorType, type IChartApi } from 'lightweight-charts';
import { cssVar } from '@/lib/format';

/** Layout options every chart is created with (transparent, app font). */
export function baseLayout(attributionLogo = true) {
  return {
    background: { type: ColorType.Solid, color: 'transparent' },
    fontSize: 11,
    fontFamily: cssVar('--font'),
    attributionLogo,
  } as const;
}

/** Grid, axis and text colours from the CSS tokens; call again whenever the theme changes. */
export function applyChartTheme(chart: IChartApi) {
  const grid = cssVar('--grid');
  const axis = cssVar('--axis');
  chart.applyOptions({
    layout: { textColor: cssVar('--text-muted') },
    grid: { vertLines: { color: grid }, horzLines: { color: grid } },
    rightPriceScale: { borderColor: axis },
    timeScale: { borderColor: axis },
  });
}

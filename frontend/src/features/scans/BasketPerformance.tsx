import { useMemo } from 'react';
import type { PerformancePoint, ScanPerformance, ScanRow } from '@/api/types';
import { LineChart, type LineSpec } from '@/components/charts';
import { Card, Delta, ErrorMessage, Skeleton, StatTile, type Column } from '@/components/ui';
import { useThemeVersion } from '@/hooks/useTheme';
import { cssVar, fmt } from '@/lib/format';
import { toChartTime } from '@/lib/time';
import './scans.css';

const pct = (v: number | null | undefined) => <Delta value={v} format={fmt.pctAbs} />;
const last = (points: PerformancePoint[]) => points[points.length - 1]?.value ?? null;
const toLine = (points: PerformancePoint[]) =>
  points.filter((p) => p.value != null).map((p) => ({ time: toChartTime(p.ts), value: p.value! * 100 }));

/** "Since 14 Nov", or "14 Oct → 28 Oct" when the window has a chosen end. */
export function performanceTitle(perf: ScanPerformance, hasEnd: boolean): string {
  return hasEnd ? `${fmt.shortDate(perf.start)} → ${fmt.shortDate(perf.end)}` : `Since ${fmt.shortDate(perf.start)}`;
}

/** Table columns for each stock's close at the window end and its change since the start. */
export function performanceColumns(perf: ScanPerformance | undefined, title: string): Column<ScanRow>[] {
  if (!perf || perf.sessions === 0) return [];
  const byId = new Map(perf.stocks.map((s) => [s.instrument_id, s]));
  const change = (r: ScanRow) => byId.get(r.instrument_id)?.change ?? null;
  // A stock not counted (no bar after the start) shows no end close either.
  const close = (r: ScanRow) => (change(r) != null ? (byId.get(r.instrument_id)?.close ?? null) : null);
  return [
    {
      key: 'perf_close',
      header: `Close ${fmt.shortDate(perf.end)}`,
      value: close,
      render: (r) => (close(r) == null ? '—' : fmt.price(close(r))),
      align: 'right',
    },
    { key: 'perf_change', header: title, value: change, render: (r) => pct(change(r)), align: 'right' },
  ];
}

interface BasketPerformanceProps {
  perf: ScanPerformance | undefined;
  loading: boolean;
  error: unknown;
  title: string;
}

/** Equal-weight basket of the scan results vs the benchmark, from the scan date's close. */
export function BasketPerformance({ perf, loading, error, title }: BasketPerformanceProps) {
  const themeVersion = useThemeVersion();
  const lines = useMemo<LineSpec[]>(() => {
    if (!perf) return [];
    const out: LineSpec[] = [{ id: 'basket', label: 'Basket', color: cssVar('--series-1'), data: toLine(perf.basket) }];
    if (perf.benchmark)
      out.push({
        id: 'bench',
        label: perf.benchmark.label,
        color: cssVar('--text-muted'),
        data: toLine(perf.benchmark.points),
      });
    return out;
  }, [perf, themeVersion]);

  if (error) {
    return (
      <Card title="Performance">
        <ErrorMessage error={new Error(`Couldn't load performance. ${error instanceof Error ? error.message : ''}`)} />
      </Card>
    );
  }
  if (loading || !perf) {
    return (
      <Card title="Performance">
        <Skeleton height={220} />
      </Card>
    );
  }

  const basket = last(perf.basket);
  const bench = perf.benchmark ? last(perf.benchmark.points) : null;
  const up = perf.stocks.filter((s) => (s.change ?? 0) > 0).length;
  const down = perf.stocks.filter((s) => (s.change ?? 0) < 0).length;
  return (
    <Card
      title={title}
      subtitle={`${perf.counted} of ${perf.total} stocks · equal weight · bought at the ${fmt.shortDate(perf.start)} close · ${perf.sessions} session${perf.sessions === 1 ? '' : 's'}`}
    >
      <div className="scan-perf__tiles">
        <StatTile label="Basket" value={pct(basket)} />
        <StatTile label={perf.benchmark?.label ?? 'Benchmark'} value={pct(bench)} />
        <StatTile
          label={`Basket vs ${perf.benchmark?.label ?? 'benchmark'}`}
          value={pct(basket != null && bench != null ? basket - bench : null)}
        />
        <StatTile label="Up / down" value={`${up} / ${down}`} />
      </div>
      {perf.counted > 0 && (
        <LineChart lines={lines} height={220} format={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`} />
      )}
    </Card>
  );
}

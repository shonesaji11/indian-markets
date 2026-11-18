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

/** "12 of 13 stocks · equal weight · picked 14 Nov, bought at the next open · 5 sessions". */
export function performanceSubtitle(perf: ScanPerformance): string {
  return `${perf.counted} of ${perf.total} stocks · equal weight · picked ${fmt.shortDate(perf.start)}, bought at the next open · ${perf.sessions} session${perf.sessions === 1 ? '' : 's'}`;
}

/** The benchmark's change over the whole window (null without a benchmark). */
export const benchmarkChange = (perf: ScanPerformance) => (perf.benchmark ? last(perf.benchmark.points) : null);

interface PerformanceSummaryProps {
  perf: ScanPerformance;
  /** Label for the basket's tile and line. */
  name?: string;
  /** Last tile shows how many stocks beat the benchmark instead of how many are up / down. */
  beatCount?: boolean;
}

/** Tiles (basket, benchmark, the gap between them, up / down or beat count) and both lines since the pick. */
export function PerformanceSummary({ perf, name = 'Basket', beatCount = false }: PerformanceSummaryProps) {
  const themeVersion = useThemeVersion();
  const lines = useMemo<LineSpec[]>(() => {
    const out: LineSpec[] = [{ id: 'basket', label: name, color: cssVar('--series-1'), data: toLine(perf.basket) }];
    if (perf.benchmark)
      out.push({
        id: 'bench',
        label: perf.benchmark.label,
        color: cssVar('--text-muted'),
        data: toLine(perf.benchmark.points),
      });
    return out;
  }, [perf, name, themeVersion]);

  const basket = last(perf.basket);
  const bench = benchmarkChange(perf);
  const benchLabel = perf.benchmark?.label ?? 'benchmark';
  const changes = perf.stocks.flatMap((s) => (s.change == null ? [] : [s.change]));
  const up = changes.filter((c) => c > 0).length;
  const down = changes.filter((c) => c < 0).length;
  return (
    <>
      <div className="scan-perf__tiles">
        <StatTile label={name} value={pct(basket)} />
        <StatTile label={perf.benchmark?.label ?? 'Benchmark'} value={pct(bench)} />
        <StatTile label={`${name} vs ${benchLabel}`} value={pct(basket != null && bench != null ? basket - bench : null)} />
        {beatCount ? (
          <StatTile
            label={`Beat ${benchLabel}`}
            value={bench == null ? '—' : `${changes.filter((c) => c > bench).length} of ${changes.length}`}
          />
        ) : (
          <StatTile label="Up / down" value={`${up} / ${down}`} />
        )}
      </div>
      {perf.counted > 0 && (
        <LineChart lines={lines} height={220} format={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`} />
      )}
    </>
  );
}

/** Equal-weight basket of the scan results vs the benchmark, bought at the open after the scan date. */
export function BasketPerformance({ perf, loading, error, title }: BasketPerformanceProps) {
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

  return (
    <Card title={title} subtitle={performanceSubtitle(perf)}>
      <PerformanceSummary perf={perf} />
    </Card>
  );
}

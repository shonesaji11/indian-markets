import { useMemo } from 'react';
import type { NearHigh, RankBy, ScanAgo, SectorBreadth, SectorBreadthRow, SectorRotation, SectorRotationRow } from '@/api/types';
import {
  Card,
  DataTable,
  Delta,
  ErrorMessage,
  Field,
  Meter,
  SegmentedControl,
  TextInput,
  type Column,
} from '@/components/ui';
import { AgoInput } from '@/features/scans/AgoInput';
import { agoValueError } from '@/features/scans/filterTree';
import { NearHighPicker, highLabel, highShort } from './NearHighPicker';

export type SectorMode = 'latest' | 'rotation';

const MODE_OPTIONS = [
  { value: 'latest' as const, label: 'Latest' },
  { value: 'rotation' as const, label: 'Rotation' },
];

const RANK_BY_OPTIONS = [
  { value: 'ma' as const, label: 'Above MA' },
  { value: 'near_high' as const, label: 'Near high' },
];

interface RotationProps {
  data: SectorRotation | undefined;
  loading: boolean;
  error: unknown;
  rankBy: RankBy;
  onRankByChange: (rankBy: RankBy) => void;
  period: number;
  onPeriodChange: (period: number) => void;
  /** Undefined = not set yet ("now" can't be compared with itself). */
  ago: ScanAgo | undefined;
  onAgoChange: (ago: ScanAgo | undefined) => void;
}

interface SectorBreadthCardProps {
  mode: SectorMode;
  onModeChange: (mode: SectorMode) => void;
  data: SectorBreadth | undefined;
  loading: boolean;
  error: unknown;
  periods: number[];
  onPeriodsChange: (periods: number[]) => void;
  /** Near-high settings: the Latest view's column and the rotation's "Near high" ranking. */
  near: NearHigh;
  onNearChange: (near: NearHigh) => void;
  rotation: RotationProps;
  minStocks: number;
  onMinStocksChange: (n: number) => void;
  /** Opens the sector's own page. */
  onSelect: (industry: string) => void;
}

const share = (r: SectorBreadthRow, p: number) => (r.stocks ? (r.above[String(p)] ?? 0) / r.stocks : null);
const nearShare = (r: SectorBreadthRow) => (r.near_high?.stocks ? r.near_high.near / r.near_high.stocks : null);
const positive = (value: string) => Math.max(1, parseInt(value, 10) || 1);
const rank = (v: number | null) => (v == null ? '—' : v.toFixed(1));
const agoText = (ago: ScanAgo) => `${ago.n}${ago.unit}`;
const round = (v: number | null, digits: number) => (v == null ? null : Number(v.toFixed(digits)) || 0);

/**
 * Sectors by the share of their stocks above a moving average, or near their 52-week / all-time high.
 * Latest: on the latest session. Rotation: change in average rank by either measure (last 5 sessions
 * vs 5 sessions ending N d/w/m earlier).
 */
export function SectorBreadthCard({
  mode, onModeChange, data, loading, error, periods, onPeriodsChange, near, onNearChange, rotation, minStocks,
  onMinStocksChange, onSelect,
}: SectorBreadthCardProps) {
  const rows = useMemo(() => (data?.sectors ?? []).filter((r) => r.stocks >= minStocks), [data, minStocks]);
  const isRotation = mode === 'rotation';
  const hidden = isRotation ? (rotation.data?.hidden ?? 0) : (data?.sectors.length ?? 0) - rows.length;
  const agoHint = rotation.ago ? agoValueError(rotation.ago) : 'Pick how far back to compare (1d to 12m).';

  const columns: Column<SectorBreadthRow>[] = useMemo(
    () => [
      { key: 'industry', header: 'Sector', value: (r) => r.industry, render: (r) => `${r.industry} ›` },
      { key: 'stocks', header: 'Stocks', value: (r) => r.stocks, align: 'right' },
      ...periods.map((p) => ({
        key: `above_${p}`,
        header: `Above ${p} MA`,
        value: (r: SectorBreadthRow) => share(r, p),
        render: (r: SectorBreadthRow) => <Meter label={`${r.above[String(p)] ?? 0} of ${r.stocks}`} value={share(r, p)} />,
      })),
      {
        key: 'near_high',
        header: `Within ${near.pct}% of ${highShort(near.basis)} high`,
        value: nearShare,
        render: (r: SectorBreadthRow) =>
          r.near_high ? <Meter label={`${r.near_high.near} of ${r.near_high.stocks}`} value={nearShare(r)} /> : '–',
      },
    ],
    [periods, near],
  );

  const rotationData = rotation.data;
  const rotationColumns: Column<SectorRotationRow>[] = useMemo(() => {
    const p = rotationData?.period ?? rotation.period;
    const window = rotationData?.window ?? 5;
    const then = rotationData ? agoText(rotationData.ago) : '';
    // Short header; the subtitle says which high and how close.
    const measure = rotationData?.rank_by === 'near_high' ? 'Near high' : `Above ${p} MA`;
    return [
      { key: 'industry', header: 'Sector', value: (r) => r.industry, render: (r) => `${r.industry} ›` },
      { key: 'stocks', header: 'Stocks', value: (r) => r.stocks, align: 'right' },
      { key: 'rank_then', header: `Avg rank ${then} ago`, value: (r) => r.rank_then, render: (r) => rank(r.rank_then), align: 'right' },
      { key: 'rank_now', header: 'Avg rank now', value: (r) => r.rank_now, render: (r) => rank(r.rank_now), align: 'right' },
      {
        key: 'rank_change',
        header: 'Rank change',
        value: (r) => r.rank_change,
        // Rounded before Delta picks the sign, so a tiny change shows as a flat 0.0, not −0.0.
        render: (r) => <Delta value={round(r.rank_change, 1)} format={(v) => v.toFixed(1)} arrow />,
        align: 'right',
      },
      {
        key: 'share_now',
        header: `${measure} (${window}-day avg)`,
        value: (r) => r.share_now,
        render: (r) => `${Math.round(r.share_now * 100)}%`,
        align: 'right',
      },
      {
        key: 'share_change',
        header: 'Δ pts',
        value: (r) => (r.share_then == null ? null : r.share_now - r.share_then),
        render: (r) => (
          <Delta value={r.share_then == null ? null : round((r.share_now - r.share_then) * 100, 0)} format={(v) => v.toFixed(0)} />
        ),
        align: 'right',
      },
    ];
  }, [rotationData, rotation.period]);
  // What the rotation ranks by, for its subtitle: "% above 50 MA" / "% within 10% of 52-week high".
  const rankedBy = rotationData
    ? rotationData.rank_by === 'near_high'
      ? `% within ${rotationData.near_pct}% of ${highLabel(rotationData.near_basis)} high`
      : `% above ${rotationData.period} MA`
    : '';

  const setPeriod = (i: number, value: string) => {
    const next = [...periods];
    next[i] = positive(value);
    onPeriodsChange(next);
  };

  const hiddenText = hidden > 0 ? ` · ${hidden} smaller sectors hidden` : '';
  const subtitle = isRotation
    ? rotationData?.as_of
      ? `Avg rank by ${rankedBy} · last ${rotationData.window} sessions vs ${rotationData.window} sessions ending ${agoText(rotationData.ago)} ago${hiddenText}`
      : 'Change in each sector\'s average rank by % of stocks above the MA or near their high'
    : `% of each sector's stocks above their moving average, and within ${near.pct}% of their ${highLabel(near.basis)} high · daily bars${hiddenText}`;

  return (
    <Card
      title="Sector breadth"
      subtitle={subtitle}
      actions={
        <>
          <Field label="View">
            <SegmentedControl value={mode} options={MODE_OPTIONS} onChange={onModeChange} aria-label="Sector breadth view" />
          </Field>
          {isRotation ? (
            <>
              <Field label="Rank by">
                <SegmentedControl
                  value={rotation.rankBy}
                  options={RANK_BY_OPTIONS}
                  onChange={rotation.onRankByChange}
                  aria-label="Rank sectors by"
                />
              </Field>
              {rotation.rankBy === 'ma' ? (
                <Field label="MA">
                  <TextInput
                    type="number"
                    min={1}
                    style={{ width: 70 }}
                    value={rotation.period}
                    onChange={(e) => rotation.onPeriodChange(positive(e.target.value))}
                  />
                </Field>
              ) : (
                <Field label="Near high">
                  <NearHighPicker value={near} onChange={onNearChange} />
                </Field>
              )}
              <Field label="Compare with">
                <AgoInput
                  value={rotation.ago}
                  onChange={rotation.onAgoChange}
                  nowTitle="Enter how far back to compare"
                  invalid={!rotation.ago}
                />
              </Field>
            </>
          ) : (
            <>
              {periods.map((p, i) => (
                <Field key={i} label={`MA ${i + 1}`}>
                  <TextInput type="number" min={1} style={{ width: 70 }} value={p} onChange={(e) => setPeriod(i, e.target.value)} />
                </Field>
              ))}
              <Field label="Near high">
                <NearHighPicker value={near} onChange={onNearChange} />
              </Field>
            </>
          )}
          <Field label="Min stocks">
            <TextInput
              type="number"
              min={1}
              style={{ width: 70 }}
              value={minStocks}
              onChange={(e) => onMinStocksChange(positive(e.target.value))}
            />
          </Field>
        </>
      }
      divided
      flush
    >
      {isRotation ? (
        <>
          <ErrorMessage error={agoHint ?? rotation.error} />
          <DataTable
            key="rotation"
            columns={rotationColumns}
            rows={rotationData?.sectors ?? []}
            rowKey={(r) => r.industry}
            onRowClick={(r) => onSelect(r.industry)}
            initialSort={{ key: 'rank_change', desc: true }}
            empty={
              rotation.loading
                ? 'Loading…'
                : 'No sectors with enough stocks. Lower "Min stocks" or check the universe has daily data.'
            }
            dense
          />
        </>
      ) : (
        <>
          <ErrorMessage error={error} />
          <DataTable
            key="latest"
            columns={columns}
            rows={rows}
            rowKey={(r) => r.industry}
            onRowClick={(r) => onSelect(r.industry)}
            initialSort={{ key: `above_${periods[periods.length - 1]}`, desc: true }}
            empty={loading ? 'Loading…' : 'No sectors with enough stocks. Lower "Min stocks" or check the universe has daily data.'}
            dense
          />
        </>
      )}
    </Card>
  );
}

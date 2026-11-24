import { useMemo } from 'react';
import { useMoverDays, useMovers } from '@/api/queries';
import type { MoverList, MoverRow } from '@/api/types';
import { Button, Card, DataTable, Delta, EmptyState, ErrorMessage, PageHeader, Skeleton, type Column } from '@/components/ui';
import { shortSymbol, useOpenChart } from '@/features/charts/chartList';
import { CutoffPicker, MoverDatePicker, dayLabel, hitPct } from '@/features/movers/MoverPickers';
import { numberCodec, useUrlState } from '@/hooks/useUrlState';
import { fmt } from '@/lib/format';

const pct0 = (v: number | null | undefined) => (v == null ? '' : `${Math.round(v * 100)}%`);
const pct1 = (v: number | null | undefined) => (v == null ? '' : `${(v * 100).toFixed(1)}%`);

/** One line under the controls: what the list is for, or how it did. */
function summary(d: MoverList): string {
  const listed = d.listed ?? 0;
  if (!d.next_session) return `${listed} stock${listed === 1 ? '' : 's'} for the next session · direction unknown`;
  const counted = d.listed_with_bar ?? 0;
  const missing = listed - counted;
  return [
    `${dayLabel(d.next_session)}: ${d.hits} of ${counted} moved ≥ ${Math.round(d.big_move * 100)}%${counted ? ` (${hitPct(d.hits ?? 0, counted)})` : ''}`,
    missing > 0 ? `${missing} didn't trade` : '',
    d.all_with_bar ? `all scored stocks that day ${hitPct(d.all_hits ?? 0, d.all_with_bar)}` : '',
  ]
    .filter(Boolean)
    .join(' · ');
}

/** Big movers: stocks the model expects to move ≥ 4% open to close on the next session, and how past lists did. */
export function MoversPage() {
  const [asOfParam, setAsOf] = useUrlState('as_of', '');
  const [cutoffParam, setCutoff] = useUrlState('cutoff', 0, numberCodec);
  const cutoff = cutoffParam > 0 && cutoffParam < 1 ? cutoffParam : undefined; // else the backend's setting
  const list = useMovers(asOfParam || undefined, cutoff);
  const days = useMoverDays(cutoff);
  const openChart = useOpenChart();
  const d = list.data;
  const past = !!d?.next_session;

  const rank = useMemo(() => new Map((d?.rows ?? []).map((r, i) => [r.instrument_id, i + 1])), [d]);
  const columns: Column<MoverRow>[] = [
    { key: 'rank', header: '#', value: (r) => rank.get(r.instrument_id) ?? 0 },
    { key: 'symbol', header: 'Stock', value: (r) => shortSymbol(r.symbol) },
    { key: 'probability', header: 'Probability', align: 'right', value: (r) => r.probability, render: (r) => pct0(r.probability) },
    ...(past
      ? ([
          {
            key: 'move',
            header: `Close vs open, ${fmt.shortDate(d?.next_session)}`,
            align: 'right',
            value: (r) => r.move,
            render: (r) => (r.move == null ? <span className="muted">No bar</span> : <Delta value={r.move} format={fmt.pctAbs} />),
          },
          {
            key: 'hit',
            header: `≥ ${Math.round((d?.big_move ?? 0.04) * 100)}%`,
            align: 'right',
            value: (r) => (r.hit ? 1 : 0),
            render: (r) => (r.hit ? <span className="movers-page__hit" aria-label="moved big">✓</span> : ''),
          },
        ] as Column<MoverRow>[])
      : ([
          { key: 'atr', header: 'ATR %', align: 'right', value: (r) => r.atr_pct, render: (r) => pct1(r.atr_pct) },
          { key: 'close', header: 'Close', align: 'right', value: (r) => r.close, render: (r) => fmt.price(r.close) },
          {
            key: 'change',
            header: 'Change',
            align: 'right',
            value: (r) => r.change,
            render: (r) => <Delta value={r.change} format={fmt.pctAbs} />,
          },
        ] as Column<MoverRow>[])),
  ];

  const open = (r: MoverRow, shown: MoverRow[]) =>
    openChart(r.instrument_id, {
      title: `Big movers after ${d?.as_of ? dayLabel(d.as_of) : ''}`,
      items: shown.map((x) => ({ instrument_id: x.instrument_id, symbol: x.symbol, change: past ? x.move : x.change })),
    });

  let body;
  if (list.isPending) {
    body = (
      <>
        <Skeleton height={12} />
        <Skeleton height={12} width="70%" style={{ marginTop: 8 }} />
      </>
    );
  } else if (list.error) {
    body = (
      <>
        <ErrorMessage error={list.error} />
        <Button size="sm" onClick={() => list.refetch()}>
          Retry
        </Button>
      </>
    );
  } else if (d && !d.as_of) {
    body = <EmptyState>No lists yet. One is scored after each evening's update.</EmptyState>;
  } else if (d && !d.scored) {
    body = <EmptyState>No list for {dayLabel(d.as_of!)}. Lists are scored for trading days only.</EmptyState>;
  } else if (d) {
    body = (
      <>
        {d.rows.length > 0 && <div className="muted movers-page__summary">{summary(d)}</div>}
        <DataTable
          columns={columns}
          rows={d.rows}
          rowKey={(r) => r.instrument_id}
          onRowClick={open}
          empty={`No stocks at p ≥ ${d.cutoff.toFixed(2)} after ${dayLabel(d.as_of!)}.${
            d.top_probability != null ? ` Highest was ${pct0(d.top_probability)}.` : ''
          }`}
          dense
        />
      </>
    );
  }

  return (
    <div className="page">
      <PageHeader
        title="Big movers"
        subtitle="Stocks the model expects to move 4% or more from open to close on the next session. It doesn't say which way."
      />
      <Card>
        <div className="movers-page__bar">
          <MoverDatePicker value={d?.as_of ?? null} days={days.data ?? []} onChange={setAsOf} />
          <CutoffPicker
            value={d?.cutoff ?? cutoff ?? 0.2}
            standard={d?.default_cutoff ?? 0.2}
            onChange={(c) => setCutoff(c === d?.default_cutoff ? 0 : c)}
          />
        </div>
        {body}
      </Card>
    </div>
  );
}

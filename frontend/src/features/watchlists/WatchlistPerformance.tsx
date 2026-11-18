import { useMemo, type ReactNode } from 'react';
import { useScanPerformance, useWatchlistQuotes } from '@/api/queries';
import type { ScanPerformance, WatchlistQuote } from '@/api/types';
import {
  Card,
  DataTable,
  Delta,
  EmptyState,
  ErrorMessage,
  Field,
  Skeleton,
  TextInput,
  sortCodec,
  type Column,
  type SortState,
} from '@/components/ui';
import { shortSymbol } from '@/features/charts/chartList';
import { PerformanceSummary, benchmarkChange, performanceSubtitle } from '@/features/scans/BasketPerformance';
import { useUrlState } from '@/hooks/useUrlState';
import { fmt } from '@/lib/format';
import { useActiveWatchlist } from './useActiveWatchlist';

type Stock = ScanPerformance['stocks'][number];
interface Row {
  instrument_id: number;
  symbol: string;
  /** Missing when the stock had no bar on the pick session (listed later, or suspended that day). */
  stock?: Stock;
  /** Change minus the benchmark's over the same window. */
  vsBench: number | null;
}

const DEFAULT_SORT: SortState = { key: 'change', desc: true };
const pct = (v: number | null | undefined) => <Delta value={v} format={fmt.pctAbs} />;
/** Percentage points, e.g. "+6.3 pts". */
const pts = (v: number | null) => <Delta value={v} format={(x) => `${(x * 100).toFixed(1)} pts`} />;

function toRows(quotes: WatchlistQuote[], perf: ScanPerformance): Row[] {
  const byId = new Map(perf.stocks.map((s) => [s.instrument_id, s]));
  const bench = benchmarkChange(perf);
  return quotes.map((q) => {
    const stock = byId.get(q.instrument_id);
    const change = stock?.change ?? null;
    return {
      instrument_id: q.instrument_id,
      symbol: shortSymbol(q.symbol),
      stock,
      vsBench: change != null && bench != null ? change - bench : null,
    };
  });
}

function columns(perf: ScanPerformance): Column<Row>[] {
  const entryDay = perf.basket[1]?.ts;
  const counted = (r: Row) => r.stock?.change != null;
  return [
    { key: 'symbol', header: 'Stock', value: (r) => r.symbol },
    {
      key: 'entry',
      header: `Entry (${fmt.shortDate(entryDay)} open)`,
      value: (r) => r.stock?.entry ?? null,
      render: (r) => (counted(r) ? fmt.price(r.stock!.entry) : '—'),
      align: 'right',
    },
    {
      key: 'close',
      header: `Close ${fmt.shortDate(perf.end)}`,
      value: (r) => (counted(r) ? (r.stock!.close ?? null) : null),
      render: (r) => (counted(r) ? fmt.price(r.stock!.close) : '—'),
      align: 'right',
    },
    {
      key: 'change',
      header: 'Change',
      value: (r) => r.stock?.change ?? null,
      render: (r) =>
        counted(r) ? pct(r.stock!.change) : <span className="muted">No bar on {fmt.shortDate(perf.start)}</span>,
      align: 'right',
    },
    {
      key: 'vs',
      header: `vs ${perf.benchmark?.label ?? 'benchmark'}`,
      value: (r) => r.vsBench,
      render: (r) => (r.vsBench == null ? '—' : pts(r.vsBench)),
      align: 'right',
    },
  ];
}

interface WatchlistPerformanceProps {
  /** The Chart | Performance switch, shown as the card's title. */
  viewSwitch: ReactNode;
  /** A row was clicked: show that stock's chart. */
  onOpenChart: (instrumentId: number) => void;
}

/** How your list's current stocks did since a date you pick (bought at the next open), vs the benchmark. URL: `from`, `until`, `sort`. */
export function WatchlistPerformance({ viewSwitch, onOpenChart }: WatchlistPerformanceProps) {
  const { lists, active } = useActiveWatchlist();
  const quotes = useWatchlistQuotes(active?.watchlist_id);
  const [from, setFrom] = useUrlState('from');
  const [until, setUntil] = useUrlState('until');
  const [sort, setSort] = useUrlState('sort', DEFAULT_SORT, sortCodec);
  const untilError = from && until && until < from ? 'Until must be after the From date.' : null;

  const ids = active?.member_ids;
  const request = useMemo(
    () =>
      from && !untilError && ids?.length ? { instrument_ids: ids, start: from, end: until || undefined } : undefined,
    [from, until, untilError, ids],
  );
  const perf = useScanPerformance(request);
  const rows = useMemo(
    () => (perf.data && quotes.data ? toRows(quotes.data, perf.data) : []),
    [perf.data, quotes.data],
  );
  const cols = useMemo(() => (perf.data ? columns(perf.data) : []), [perf.data]);
  const ready = perf.data && perf.data.sessions > 0 && quotes.data;

  let body: ReactNode; // everything but the populated view, which runs its table edge to edge
  if (lists.error || quotes.error || perf.error) {
    body = <ErrorMessage error={lists.error ?? quotes.error ?? perf.error} />;
  } else if (lists.isLoading) {
    body = <Skeleton height={220} />;
  } else if (!active) {
    body = <EmptyState>Create a watchlist in the pane on the right to track how it does.</EmptyState>;
  } else if (!active.member_ids.length) {
    body = <EmptyState>This list is empty. Add stocks with the ☆ on any chart.</EmptyState>;
  } else if (!from) {
    body = <EmptyState>Pick the date you started this list to see how it has done since.</EmptyState>;
  } else if (untilError) {
    body = null;
  } else if (perf.isLoading || quotes.isLoading) {
    body = <Skeleton height={220} />;
  } else if (!ready) {
    body = (
      <EmptyState>
        Stocks are bought at the open of the first session after {fmt.shortDate(from)}. Check back after it.
      </EmptyState>
    );
  }
  const content = body === undefined && ready && active ? (
    <>
      <div style={{ padding: 'var(--space-4) var(--space-4) 0' }}>
        <PerformanceSummary perf={perf.data!} name={active.name} beatCount />
      </div>
      <DataTable
        columns={cols}
        rows={rows}
        rowKey={(r) => r.instrument_id}
        sort={sort}
        onSortChange={setSort}
        onRowClick={(r) => onOpenChart(r.instrument_id)}
      />
    </>
  ) : (
    body && <div style={{ padding: 'var(--space-4)' }}>{body}</div>
  );

  return (
    <Card
      title={viewSwitch}
      subtitle={ready ? `${performanceSubtitle(perf.data!)} · stocks in the list now` : undefined}
      actions={
        <>
          <Field label="From">
            <TextInput type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field label="Until">
            <TextInput type="date" value={until} min={from || undefined} onChange={(e) => setUntil(e.target.value)} />
            {untilError && <span className="scan-perf__error">{untilError}</span>}
          </Field>
        </>
      }
      divided
      flush
    >
      {content}
    </Card>
  );
}

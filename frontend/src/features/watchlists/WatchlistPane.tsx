import { useEffect, useMemo, useState } from 'react';
import {
  useCreateWatchlist,
  useDeleteWatchlist,
  useRenameWatchlist,
  useSetWatchlistMember,
  useWatchlistQuotes,
} from '@/api/queries';
import type { WatchlistQuote } from '@/api/types';
import { Button, ErrorMessage, Popover, Skeleton } from '@/components/ui';
import type { ChartList } from '@/features/charts/chartList';
import { RelatedList, type SidePaneProps } from '@/features/charts/RelatedList';
import { useUrlUpdate } from '@/hooks/useUrlState';
import { fmt } from '@/lib/format';
import { NameForm } from './NameForm';
import { useActiveWatchlist } from './useActiveWatchlist';
import './watchlists.css';

/** Stocks in the list's order; a stock whose last bar is older than the list's newest shows that date. */
function toChartList(name: string, quotes: WatchlistQuote[]): ChartList {
  const newest = quotes.reduce<string | null>((m, q) => (q.ts && (!m || q.ts > m) ? q.ts : m), null);
  return {
    title: name,
    items: quotes.map((q) => ({
      instrument_id: q.instrument_id,
      symbol: q.symbol,
      change: q.pct_change,
      close: q.close,
      note: !q.ts ? 'no data' : q.ts < newest! ? fmt.shortDate(q.ts) : undefined,
    })),
  };
}

const TrashIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <path d="M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
  </svg>
);

/** The Watchlists tab's side pane: pick, create, rename or delete a list, and step through its stocks. */
export function WatchlistPane({ current, onSelect, open, onOpenChange }: SidePaneProps) {
  const { lists, all, active } = useActiveWatchlist();
  const update = useUrlUpdate();
  const quotes = useWatchlistQuotes(active?.watchlist_id);
  const create = useCreateWatchlist();
  const rename = useRenameWatchlist();
  const remove = useDeleteWatchlist();
  const setMember = useSetWatchlistMember();
  const [picking, setPicking] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const list = useMemo(
    () => (active && quotes.data ? toChartList(active.name, quotes.data) : null),
    [active?.name, quotes.data],
  );

  // Nothing charted yet (first visit, or just switched lists): chart the list's first stock.
  useEffect(() => {
    if (current === undefined && list?.items.length) onSelect(list.items[0].instrument_id);
  }, [current, list]);

  // Switching lists clears the stock, so the effect above charts the new list's first one.
  const show = (watchlistId: string | undefined) => update({ wl: watchlistId, instrument: undefined });

  // Hidden pane (remembered per browser): RelatedList draws its own rail once a list is loaded.
  if (!open && !list) {
    return (
      <button className="chart-list chart-list--closed" onClick={() => onOpenChange(true)} title="Show the list">
        <span>Watchlists</span>
      </button>
    );
  }
  if (lists.isLoading) {
    return (
      <aside className="chart-list watchlist-pane__state">
        <Skeleton height={28} />
        <Skeleton />
        <Skeleton />
      </aside>
    );
  }
  if (lists.error || !active) {
    return (
      <aside className="chart-list watchlist-pane__state">
        <ErrorMessage error={lists.error} />
        {!lists.error && (
          <>
            <div className="watchlist-pane__heading">Create your first watchlist</div>
            <div className="muted">Name it, then add stocks with the ☆ on any chart.</div>
            <NameForm
              placeholder="Watchlist name"
              submitLabel="Create"
              autoFocus
              onSubmit={async (name) => show((await create.mutateAsync(name)).watchlist_id)}
            />
          </>
        )}
      </aside>
    );
  }

  const toolbar = renaming ? (
    <NameForm
      initial={active.name}
      placeholder="Watchlist name"
      submitLabel="Save"
      autoFocus
      onCancel={() => setRenaming(false)}
      onSubmit={async (name) => {
        await rename.mutateAsync({ id: active.watchlist_id, name });
        setRenaming(false);
      }}
    />
  ) : (
    <div className="ui-row watchlist-pane__toolbar">
      <Popover
        open={picking}
        onClose={() => setPicking(false)}
        trigger={
          <button
            type="button"
            className="watchlist-pane__picker"
            aria-expanded={picking}
            title="Choose a watchlist"
            onClick={() => setPicking(!picking)}
          >
            <span className="watchlist-pane__picker-name">{active.name}</span>
            <span aria-hidden>▾</span>
          </button>
        }
      >
        {all.map((w) => (
          <button
            key={w.watchlist_id}
            type="button"
            className="ui-popover__item"
            aria-current={w === active}
            onClick={() => {
              setPicking(false);
              if (w !== active) show(w.watchlist_id);
            }}
          >
            <span className="watchlist-star__name">{w.name}</span>
            <span className="muted">{w.member_ids.length}</span>
          </button>
        ))}
        <div className="ui-popover__section">
          <NameForm
            placeholder="New watchlist"
            submitLabel="Create"
            onSubmit={async (name) => {
              const created = await create.mutateAsync(name);
              setPicking(false);
              show(created.watchlist_id);
            }}
          />
        </div>
      </Popover>
      <Button size="sm" icon title="Rename this watchlist" onClick={() => setRenaming(true)}>
        ✎
      </Button>
      <Popover
        open={confirming}
        onClose={() => setConfirming(false)}
        align="right"
        trigger={
          <Button
            size="sm"
            icon
            title="Delete this watchlist"
            aria-expanded={confirming}
            onClick={() => setConfirming(!confirming)}
          >
            <TrashIcon />
          </Button>
        }
      >
        <div className="watchlist-pane__confirm">
          Delete “{active.name}” ({active.member_ids.length} {active.member_ids.length === 1 ? 'stock' : 'stocks'})?
          <ErrorMessage error={remove.error} />
          <div className="ui-row watchlist-pane__confirm-actions">
            <Button size="sm" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              className="watchlist-pane__delete"
              loading={remove.isPending}
              onClick={() =>
                remove.mutate(active.watchlist_id, {
                  onSuccess: () => {
                    setConfirming(false);
                    show(undefined);
                  },
                })
              }
            >
              Delete
            </Button>
          </div>
        </div>
      </Popover>
    </div>
  );

  if (!list) {
    return (
      <aside className="chart-list watchlist-pane__state">
        {toolbar}
        {quotes.error ? <ErrorMessage error={quotes.error} /> : <Skeleton />}
      </aside>
    );
  }

  return (
    <RelatedList
      list={list}
      current={current}
      onSelect={onSelect}
      open={open}
      onOpenChange={onOpenChange}
      toolbar={
        <>
          {toolbar}
          <ErrorMessage error={setMember.error} />
        </>
      }
      onRemove={(instrumentId) => setMember.mutate({ id: active.watchlist_id, instrumentId, member: false })}
      empty={<div className="muted watchlist-pane__empty">Empty. Use the ☆ on any chart to add stocks.</div>}
    />
  );
}

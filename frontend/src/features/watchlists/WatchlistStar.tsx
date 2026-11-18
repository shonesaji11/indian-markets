import { useState } from 'react';
import { useCreateWatchlist, useMyWatchlists, useSetWatchlistMember } from '@/api/queries';
import { Button, ErrorMessage, Popover } from '@/components/ui';
import { NameForm } from './NameForm';
import './watchlists.css';

/** Star in the chart header: tick the lists this stock should be in, or make a new one with it. */
export function WatchlistStar({ instrumentId }: { instrumentId: number }) {
  const [open, setOpen] = useState(false);
  const lists = useMyWatchlists();
  const setMember = useSetWatchlistMember();
  const create = useCreateWatchlist();
  const inAny = (lists.data ?? []).some((w) => w.member_ids.includes(instrumentId));

  return (
    <Popover
      open={open}
      onClose={() => setOpen(false)}
      align="right"
      trigger={
        <Button
          size="sm"
          icon
          aria-pressed={open}
          aria-expanded={open}
          title="Add to watchlist"
          className={inAny ? 'watchlist-star--on' : undefined}
          onClick={() => setOpen(!open)}
        >
          {inAny ? '★' : '☆'}
        </Button>
      }
    >
      <ErrorMessage error={lists.error ?? setMember.error} />
      {(lists.data ?? []).map((w) => {
        const member = w.member_ids.includes(instrumentId);
        return (
          <label key={w.watchlist_id} className="ui-popover__item">
            <input
              type="checkbox"
              checked={member}
              disabled={setMember.isPending}
              onChange={() => setMember.mutate({ id: w.watchlist_id, instrumentId, member: !member })}
            />
            <span className="watchlist-star__name">{w.name}</span>
          </label>
        );
      })}
      <div className={lists.data?.length ? 'ui-popover__section' : 'watchlist-star__first'}>
        <NameForm
          placeholder="New watchlist"
          submitLabel="Create"
          autoFocus={lists.data?.length === 0}
          onSubmit={async (name) => {
            const created = await create.mutateAsync(name);
            await setMember.mutateAsync({ id: created.watchlist_id, instrumentId, member: true });
          }}
        />
        <div className="muted watchlist-star__hint">Creates it and adds this stock.</div>
      </div>
    </Popover>
  );
}

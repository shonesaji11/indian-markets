import { useMyWatchlists } from '@/api/queries';
import { useUrlState } from '@/hooks/useUrlState';

/** Your lists and the one shown on the Watchlists tab (URL `wl`; an unknown or missing id = your first list). */
export function useActiveWatchlist() {
  const lists = useMyWatchlists();
  const [wlParam] = useUrlState('wl');
  const all = lists.data ?? [];
  return { lists, all, active: all.find((w) => w.watchlist_id === wlParam) ?? all[0] };
}

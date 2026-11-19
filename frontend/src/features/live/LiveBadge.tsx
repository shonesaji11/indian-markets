import { Badge } from '@/components/ui';
import type { LiveState } from './live';
import './live.css';

const time = (ts: string) => ts.slice(11, 19);

/** Live / last price / feed lost; renders nothing when no live figures are involved. */
export function LiveBadge({ state }: { state: LiveState }) {
  if (!state) return null;
  if (state.kind === 'live') {
    return (
      <Badge tone="success">
        <span className="live-dot" aria-hidden />
        Live {time(state.at)}
      </Badge>
    );
  }
  if (state.kind === 'last') return <Badge>Last price {time(state.at)} · official close after the 17:00 update</Badge>;
  return <Badge tone="warn">Live feed lost at {time(state.at)} · reconnecting · prices may be old</Badge>;
}

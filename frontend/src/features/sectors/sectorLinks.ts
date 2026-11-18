import type { ScanAgo } from '@/api/types';
import type { SortState } from '@/components/ui';
import { agoCodec } from '@/features/scans/filterTree';
import { intListCodec } from '@/hooks/useUrlState';

export const DEFAULT_UNIVERSE = 'nifty500';
/** Watchlists that make sense as a stock universe (index lists, not lists of indices). */
export const STOCK_UNIVERSES = new Set(['nifty50', 'nifty500', 'niftytotalmarket', 'nse_traded']);
export const DEFAULT_MAS = [10, 20];
export const DEFAULT_SECTOR_SORT: SortState = { key: 'pct_change', desc: true };
export const DEFAULT_ROTATION_MA = 50;
export const DEFAULT_ROTATION_AGO: ScanAgo = { n: 1, unit: 'w' };

interface SectorContext {
  universe: string;
  asOf?: string;
  mas: number[];
  /** Set while the Overview's Sector breadth card is in Rotation view. */
  rotation?: { period: number; ago: ScanAgo | undefined };
}

/** Query string carrying universe, date, MA periods and the rotation view between the Overview and a sector page. */
function contextParams({ universe, asOf, mas, rotation }: SectorContext): URLSearchParams {
  const params = new URLSearchParams();
  if (universe !== DEFAULT_UNIVERSE) params.set('universe', universe);
  if (asOf) params.set('as_of', asOf);
  if (intListCodec.format(mas) !== intListCodec.format(DEFAULT_MAS)) params.set('ma', intListCodec.format(mas));
  if (rotation) {
    params.set('sector_view', 'rotation');
    if (rotation.period !== DEFAULT_ROTATION_MA) params.set('rotation_ma', String(rotation.period));
    const ago = agoCodec.format(rotation.ago);
    if (ago !== agoCodec.format(DEFAULT_ROTATION_AGO)) params.set('ago', ago);
  }
  return params;
}

export function sectorHref(industry: string, ctx: SectorContext): string {
  const params = contextParams(ctx);
  params.set('name', industry);
  return `/sector?${params}`;
}

export function overviewHref(ctx: SectorContext): string {
  const qs = contextParams(ctx).toString();
  return qs ? `/?${qs}` : '/';
}

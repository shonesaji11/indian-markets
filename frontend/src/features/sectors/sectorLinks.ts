import type { SortState } from '@/components/ui';
import { intListCodec } from '@/hooks/useUrlState';

export const DEFAULT_UNIVERSE = 'nifty500';
export const DEFAULT_MAS = [10, 20];
export const DEFAULT_SECTOR_SORT: SortState = { key: 'pct_change', desc: true };

interface SectorContext {
  universe: string;
  asOf?: string;
  mas: number[];
}

/** Query string carrying universe, date and MA periods between the Overview and a sector page. */
function contextParams({ universe, asOf, mas }: SectorContext): URLSearchParams {
  const params = new URLSearchParams();
  if (universe !== DEFAULT_UNIVERSE) params.set('universe', universe);
  if (asOf) params.set('as_of', asOf);
  if (intListCodec.format(mas) !== intListCodec.format(DEFAULT_MAS)) params.set('ma', intListCodec.format(mas));
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

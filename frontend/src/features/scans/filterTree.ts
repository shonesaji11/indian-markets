import type { IndicatorInfo, ScanAgo, ScanCondition, ScanField, ScanGroup, ScanOp, ScanOperand } from '@/api/types';
import type { UrlCodec } from '@/hooks/useUrlState';

export const EMPTY_FILTER: ScanGroup = { type: 'group', match: 'all', items: [] };

export const OP_OPTIONS: { value: ScanOp; label: string }[] = [
  { value: 'gt', label: '>' },
  { value: 'gte', label: '≥' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '≤' },
  { value: 'crosses_above', label: 'crosses above' },
  { value: 'crosses_below', label: 'crosses below' },
];

export const newCondition = (): ScanCondition => ({
  type: 'condition',
  left: { type: 'field', field: 'close' },
  op: 'gt',
  right: { type: 'value', value: null },
});

export const newGroup = (match: ScanGroup['match'] = 'any'): ScanGroup => ({ type: 'group', match, items: [newCondition()] });

/** Sessions per "ago" unit and the furthest back an operand may read; mirrors engine/screener.py. */
export const AGO_UNITS: Record<ScanAgo['unit'], number> = { d: 1, w: 5, m: 21 };
export const MAX_AGO_BARS = 252;

/** Message when an offset is invalid, else null (no offset = now, which is valid). */
export function agoValueError(ago: ScanAgo | undefined): string | null {
  if (!ago) return null;
  return Number.isInteger(ago.n) && ago.n >= 0 && ago.n * AGO_UNITS[ago.unit] <= MAX_AGO_BARS
    ? null
    : `Up to 12 months back (${MAX_AGO_BARS} sessions), whole numbers only.`;
}

/** Message when an operand's offset is invalid, else null. */
export const agoError = (op: ScanOperand) => agoValueError(op.ago);

/** "1w" <-> {n: 1, unit: 'w'}; '' or anything else = no offset. */
export const agoCodec: UrlCodec<ScanAgo | undefined> = {
  parse: (raw) => {
    const m = /^(\d+)([dwm])$/.exec(raw);
    return m ? { n: Number(m[1]), unit: m[2] as ScanAgo['unit'] } : undefined;
  },
  format: (ago) => (ago ? `${ago.n}${ago.unit}` : ''),
};

export const conditionError = (c: ScanCondition) => agoError(c.left) ?? (c.right.type === 'value' ? null : agoError(c.right));

/** Drop conditions whose number isn't filled in yet or whose offset is invalid, and groups left empty, so half-edited rows don't run. */
export function prune(group: ScanGroup): ScanGroup {
  const items = group.items
    .map((item) => (item.type === 'group' ? prune(item) : item))
    .filter((item) =>
      item.type === 'group'
        ? item.items.length > 0
        : !conditionError(item) &&
          (item.right.type !== 'value' || (item.right.value != null && Number.isFinite(item.right.value))),
    );
  return { ...group, items };
}

/** Select value for an operand: `f:close`, `i:macd:signal`. */
export function operandValue(op: ScanOperand): string {
  return op.type === 'field' ? `f:${op.field}` : `i:${op.name}:${op.output}`;
}

export function operandFromValue(value: string, indicators: IndicatorInfo[], current?: ScanOperand): ScanOperand {
  const [kind, name, output] = value.split(':');
  // The offset belongs to the slot, so it survives picking another field or indicator.
  if (kind === 'f') return { type: 'field', field: name, ago: current?.ago };
  // Keep edited params when only the output changes (macd line -> signal).
  const params =
    current?.type === 'indicator' && current.name === name ? current.params : { ...indicators.find((i) => i.name === name)?.params };
  return { type: 'indicator', name, output, params, ago: current?.ago };
}

export function operandOptions(fields: ScanField[], indicators: IndicatorInfo[]) {
  return [
    ...fields.map((f) => ({ value: `f:${f.name}`, label: f.label })),
    ...indicators.flatMap((i) =>
      i.outputs.map((o) => ({ value: `i:${i.name}:${o}`, label: indicatorLabel(i, o) })),
    ),
  ];
}

/** `RELATIVE VOLUME`, `MACD · signal`. */
const indicatorLabel = (i: IndicatorInfo, output: string) => {
  const name = i.name.replace(/_pct$/, '%').replace(/_/g, ' ').toUpperCase();
  return i.outputs.length > 1 ? `${name} · ${output}` : name;
};

export const filterCodec: UrlCodec<ScanGroup> = {
  format: (g) => JSON.stringify(g),
  parse: (raw) => {
    try {
      const g = JSON.parse(raw);
      return g?.type === 'group' ? (g as ScanGroup) : EMPTY_FILTER;
    } catch {
      return EMPTY_FILTER;
    }
  },
};

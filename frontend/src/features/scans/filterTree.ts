import type { IndicatorInfo, ScanCondition, ScanField, ScanGroup, ScanOp, ScanOperand } from '@/api/types';
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

/** Drop conditions whose number isn't filled in yet, and groups left empty, so half-edited rows don't run. */
export function prune(group: ScanGroup): ScanGroup {
  const items = group.items
    .map((item) => (item.type === 'group' ? prune(item) : item))
    .filter((item) =>
      item.type === 'group'
        ? item.items.length > 0
        : item.right.type !== 'value' || (item.right.value != null && Number.isFinite(item.right.value)),
    );
  return { ...group, items };
}

/** Select value for an operand: `f:close`, `i:macd:signal`. */
export function operandValue(op: ScanOperand): string {
  return op.type === 'field' ? `f:${op.field}` : `i:${op.name}:${op.output}`;
}

export function operandFromValue(value: string, indicators: IndicatorInfo[], current?: ScanOperand): ScanOperand {
  const [kind, name, output] = value.split(':');
  if (kind === 'f') return { type: 'field', field: name };
  // Keep edited params when only the output changes (macd line -> signal).
  const params =
    current?.type === 'indicator' && current.name === name ? current.params : { ...indicators.find((i) => i.name === name)?.params };
  return { type: 'indicator', name, output, params };
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
  const name = i.name.replace(/_/g, ' ').toUpperCase();
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

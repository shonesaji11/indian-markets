import { useIndicators, useScanFields } from '@/api/queries';
import type { IndicatorInfo, ScanCondition, ScanField, ScanGroup, ScanOperand } from '@/api/types';
import { Button, SegmentedControl, Select, TextInput } from '@/components/ui';
import { ParamInputs } from '@/features/indicators/ParamInputs';
import { OP_OPTIONS, newCondition, newGroup, operandFromValue, operandOptions, operandValue } from './filterTree';
import './scans.css';

/** Groups nest at most this deep: enough for (A and B) or (C and (D or E)). */
const MAX_DEPTH = 3;
const MATCH_OPTIONS = [
  { value: 'all' as const, label: 'all (AND)' },
  { value: 'any' as const, label: 'any (OR)' },
];

interface Catalog {
  fields: ScanField[];
  indicators: IndicatorInfo[];
}

/** Edit a filter tree: groups match all/any of their items; items are conditions or nested groups. */
export function FilterBuilder({ value, onChange }: { value: ScanGroup; onChange: (g: ScanGroup) => void }) {
  const { data: fields = [] } = useScanFields();
  const { data: indicators = [] } = useIndicators();
  return <GroupEditor group={value} onChange={onChange} depth={1} catalog={{ fields, indicators }} />;
}

interface GroupEditorProps {
  group: ScanGroup;
  onChange: (g: ScanGroup) => void;
  onRemove?: () => void;
  depth: number;
  catalog: Catalog;
}

function GroupEditor({ group, onChange, onRemove, depth, catalog }: GroupEditorProps) {
  const setItem = (i: number, item: ScanGroup['items'][number]) =>
    onChange({ ...group, items: group.items.map((x, n) => (n === i ? item : x)) });
  const removeItem = (i: number) => onChange({ ...group, items: group.items.filter((_, n) => n !== i) });
  const add = (item: ScanGroup['items'][number]) => onChange({ ...group, items: [...group.items, item] });

  return (
    <div className={depth === 1 ? 'scan-group' : 'scan-group scan-group--nested'}>
      <div className="ui-row scan-group__head">
        <span className="muted">Match</span>
        <SegmentedControl
          value={group.match}
          options={MATCH_OPTIONS}
          onChange={(match) => onChange({ ...group, match })}
          aria-label="Combine conditions with"
        />
        <span className="muted">of these</span>
        <div style={{ flex: 1 }} />
        {onRemove && (
          <Button size="sm" variant="ghost" icon onClick={onRemove} aria-label="Remove group" title="Remove group">
            ×
          </Button>
        )}
      </div>

      {group.items.length === 0 && depth === 1 && (
        <div className="muted scan-group__empty">No conditions: every stock in the universe is shown.</div>
      )}

      {group.items.map((item, i) =>
        item.type === 'group' ? (
          <GroupEditor
            key={i}
            group={item}
            onChange={(g) => setItem(i, g)}
            onRemove={() => removeItem(i)}
            depth={depth + 1}
            catalog={catalog}
          />
        ) : (
          <ConditionRow key={i} cond={item} onChange={(c) => setItem(i, c)} onRemove={() => removeItem(i)} catalog={catalog} />
        ),
      )}

      <div className="ui-row scan-group__actions">
        <Button size="sm" onClick={() => add(newCondition())}>
          + Condition
        </Button>
        {depth < MAX_DEPTH && (
          <Button size="sm" onClick={() => add(newGroup(group.match === 'all' ? 'any' : 'all'))}>
            + Group
          </Button>
        )}
      </div>
    </div>
  );
}

interface ConditionRowProps {
  cond: ScanCondition;
  onChange: (c: ScanCondition) => void;
  onRemove: () => void;
  catalog: Catalog;
}

function ConditionRow({ cond, onChange, onRemove, catalog }: ConditionRowProps) {
  const percent = cond.left.type === 'field' && catalog.fields.find((f) => f.name === (cond.left as { field: string }).field)?.percent;
  const right = cond.right;

  return (
    <div className="ui-row scan-condition">
      <OperandEditor operand={cond.left} onChange={(left) => onChange({ ...cond, left })} catalog={catalog} />
      <Select value={cond.op} options={OP_OPTIONS} onChange={(op) => onChange({ ...cond, op })} aria-label="Comparison" />
      <Select
        value={right.type === 'value' ? 'value' : operandValue(right)}
        options={[{ value: 'value', label: 'Value' }, ...operandOptions(catalog.fields, catalog.indicators)]}
        onChange={(v) =>
          onChange({
            ...cond,
            right: v === 'value' ? { type: 'value', value: null } : operandFromValue(v, catalog.indicators, right.type === 'value' ? undefined : right),
          })
        }
        aria-label="Compare with"
      />
      {right.type === 'value' ? (
        <span className="ui-row scan-condition__value">
          <TextInput
            type="number"
            style={{ width: 90 }}
            value={right.value ?? ''}
            placeholder={percent ? '2.5' : '0'}
            onChange={(e) => onChange({ ...cond, right: { type: 'value', value: e.target.value === '' ? null : Number(e.target.value) } })}
            aria-label="Value"
          />
          {percent && <span className="muted">%</span>}
        </span>
      ) : (
        right.type === 'indicator' && <IndicatorParams operand={right} onChange={(r) => onChange({ ...cond, right: r })} catalog={catalog} />
      )}
      <div style={{ flex: 1 }} />
      <Button size="sm" variant="ghost" icon onClick={onRemove} aria-label="Remove condition" title="Remove condition">
        ×
      </Button>
    </div>
  );
}

function OperandEditor({ operand, onChange, catalog }: { operand: ScanOperand; onChange: (o: ScanOperand) => void; catalog: Catalog }) {
  return (
    <>
      <Select
        value={operandValue(operand)}
        options={operandOptions(catalog.fields, catalog.indicators)}
        onChange={(v) => onChange(operandFromValue(v, catalog.indicators, operand))}
        aria-label="Field or indicator"
      />
      {operand.type === 'indicator' && <IndicatorParams operand={operand} onChange={onChange} catalog={catalog} />}
    </>
  );
}

function IndicatorParams({
  operand,
  onChange,
  catalog,
}: {
  operand: Extract<ScanOperand, { type: 'indicator' }>;
  onChange: (o: ScanOperand) => void;
  catalog: Catalog;
}) {
  const spec = catalog.indicators.find((i) => i.name === operand.name);
  if (!spec) return null;
  return <ParamInputs defaults={spec.params} params={operand.params} onChange={(params) => onChange({ ...operand, params })} labelled={false} />;
}

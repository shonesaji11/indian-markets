import type { ScanAgo } from '@/api/types';
import { Select, TextInput } from '@/components/ui';
import { AGO_UNITS, agoValueError } from './filterTree';
import './scans.css';

const UNIT_OPTIONS = (Object.keys(AGO_UNITS) as ScanAgo['unit'][]).map((u) => ({ value: u, label: `${u} ago` }));

interface AgoInputProps {
  value: ScanAgo | undefined;
  /** Clearing the number (or 0) gives undefined, i.e. now. */
  onChange: (ago: ScanAgo | undefined) => void;
  /** Tooltip when there's no offset. */
  nowTitle?: string;
  /** Show as invalid even when the offset itself is fine (e.g. where "now" isn't allowed). */
  invalid?: boolean;
}

/** "now", or N d/w/m ago (1/5/21 trading sessions each). Used by scan conditions and sector rotation. */
export function AgoInput({
  value: ago,
  onChange,
  nowTitle = 'Value on the scan day; enter a number to look back',
  invalid = false,
}: AgoInputProps) {
  const set = (next: ScanAgo | undefined) => onChange(next && next.n !== 0 ? next : undefined);
  const sessions = ago ? ago.n * AGO_UNITS[ago.unit] : 0;
  return (
    <span
      className={`scan-ago${ago ? ' scan-ago--set' : ''}${invalid || agoValueError(ago) ? ' scan-ago--error' : ''}`}
      title={ago ? `= ${sessions} trading session${sessions === 1 ? '' : 's'} back` : nowTitle}
    >
      <TextInput
        type="number"
        min={0}
        step={1}
        className="scan-ago__n"
        placeholder="now"
        value={ago?.n ?? ''}
        onChange={(e) => set(e.target.value === '' ? undefined : { n: Number(e.target.value), unit: ago?.unit ?? 'd' })}
        aria-label="How far back"
      />
      {ago && (
        <Select
          value={ago.unit}
          options={UNIT_OPTIONS}
          onChange={(unit) => set({ ...ago, unit })}
          className="scan-ago__unit"
          aria-label="Unit"
        />
      )}
    </span>
  );
}

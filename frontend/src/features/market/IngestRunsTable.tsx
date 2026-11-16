import { useIngestRuns } from '@/api/queries';
import type { IngestRun } from '@/api/types';
import { Badge, Card, DataTable, ErrorMessage, type Column } from '@/components/ui';
import { fmt } from '@/lib/format';
import { formatDate, formatDateTime } from '@/lib/time';

const tone = { ok: 'success', error: 'danger', running: 'warn' } as const;

const columns: Column<IngestRun>[] = [
  { key: 'started', header: 'Started', value: (r) => r.started_at, render: (r) => formatDateTime(r.started_at) },
  { key: 'symbol', header: 'Instrument', value: (r) => `${r.exchange}:${r.symbol}` },
  { key: 'timeframe', header: 'Interval', value: (r) => r.timeframe },
  { key: 'window', header: 'Window', render: (r) => `${formatDate(r.window_start)} → ${formatDate(r.window_end)}` },
  { key: 'status', header: 'Status', value: (r) => r.status, render: (r) => <Badge tone={tone[r.status]}>{r.status}</Badge> },
  { key: 'rows', header: 'Bars written', value: (r) => r.rows_written, render: (r) => fmt.int(r.rows_written), align: 'right' },
  { key: 'error', header: 'Error', render: (r) => r.error ?? '' },
];

export function IngestRunsTable() {
  const { data = [], error } = useIngestRuns();
  return (
    <Card title="Recent fetches" divided flush>
      <ErrorMessage error={error} />
      <DataTable columns={columns} rows={data} rowKey={(r) => r.run_id} empty="No fetches yet" />
    </Card>
  );
}

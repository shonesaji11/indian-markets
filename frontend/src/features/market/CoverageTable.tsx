import { useNavigate } from 'react-router-dom';
import { useCoverage } from '@/api/queries';
import type { CoverageRow } from '@/api/types';
import { Card, DataTable, ErrorMessage, type Column } from '@/components/ui';
import { fmt } from '@/lib/format';
import { formatDate, formatDateTime } from '@/lib/time';

const columns: Column<CoverageRow>[] = [
  { key: 'symbol', header: 'Instrument', value: (r) => `${r.exchange}:${r.symbol}` },
  { key: 'timeframe', header: 'Interval', value: (r) => r.timeframe },
  { key: 'bars', header: 'Bars', value: (r) => r.bars, render: (r) => fmt.int(r.bars), align: 'right' },
  { key: 'first', header: 'From', value: (r) => r.first_ts, render: (r) => formatDate(r.first_ts) },
  { key: 'last', header: 'To', value: (r) => r.last_ts, render: (r) => formatDateTime(r.last_ts) },
  { key: 'ingested', header: 'Last fetched', value: (r) => r.last_ingested_at, render: (r) => formatDateTime(r.last_ingested_at) },
];

export function CoverageTable() {
  const { data = [], error } = useCoverage();
  const navigate = useNavigate();
  return (
    <Card title="Stored data" subtitle="Click a row to chart it" divided flush>
      <ErrorMessage error={error} />
      <DataTable
        columns={columns}
        rows={data}
        rowKey={(r) => `${r.instrument_id}:${r.timeframe}`}
        onRowClick={(r) => navigate(`/chart?instrument=${r.instrument_id}&interval=${r.timeframe}`)}
        empty="Nothing stored yet. Fetch some history above."
      />
    </Card>
  );
}

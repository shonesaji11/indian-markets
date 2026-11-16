import { useMemo } from 'react';
import type { SectorBreadth, SectorBreadthRow } from '@/api/types';
import { Card, DataTable, ErrorMessage, Field, Meter, TextInput, type Column } from '@/components/ui';

interface SectorBreadthCardProps {
  data: SectorBreadth | undefined;
  loading: boolean;
  error: unknown;
  periods: number[];
  onPeriodsChange: (periods: number[]) => void;
  minStocks: number;
  onMinStocksChange: (n: number) => void;
  /** Opens the sector's own page. */
  onSelect: (industry: string) => void;
}

const share = (r: SectorBreadthRow, p: number) => (r.stocks ? (r.above[String(p)] ?? 0) / r.stocks : null);

/** Sectors ranked by the share of their stocks above each moving average. */
export function SectorBreadthCard({
  data, loading, error, periods, onPeriodsChange, minStocks, onMinStocksChange, onSelect,
}: SectorBreadthCardProps) {
  const rows = useMemo(() => (data?.sectors ?? []).filter((r) => r.stocks >= minStocks), [data, minStocks]);
  const hidden = (data?.sectors.length ?? 0) - rows.length;

  const columns: Column<SectorBreadthRow>[] = useMemo(
    () => [
      { key: 'industry', header: 'Sector', value: (r) => r.industry, render: (r) => `${r.industry} ›` },
      { key: 'stocks', header: 'Stocks', value: (r) => r.stocks, align: 'right' },
      ...periods.map((p) => ({
        key: `above_${p}`,
        header: `Above ${p} MA`,
        value: (r: SectorBreadthRow) => share(r, p),
        render: (r: SectorBreadthRow) => <Meter label={`${r.above[String(p)] ?? 0} of ${r.stocks}`} value={share(r, p)} />,
      })),
    ],
    [periods],
  );

  const setPeriod = (i: number, value: string) => {
    const next = [...periods];
    next[i] = Math.max(1, parseInt(value, 10) || 1);
    onPeriodsChange(next);
  };

  return (
    <Card
      title="Sector breadth"
      subtitle={`% of each sector's stocks above their moving average · daily bars${hidden > 0 ? ` · ${hidden} smaller sectors hidden` : ''}`}
      actions={
        <>
          {periods.map((p, i) => (
            <Field key={i} label={`MA ${i + 1}`}>
              <TextInput type="number" min={1} style={{ width: 70 }} value={p} onChange={(e) => setPeriod(i, e.target.value)} />
            </Field>
          ))}
          <Field label="Min stocks">
            <TextInput
              type="number"
              min={1}
              style={{ width: 70 }}
              value={minStocks}
              onChange={(e) => onMinStocksChange(Math.max(1, parseInt(e.target.value, 10) || 1))}
            />
          </Field>
        </>
      }
      divided
      flush
    >
      <ErrorMessage error={error} />
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => r.industry}
        onRowClick={(r) => onSelect(r.industry)}
        initialSort={{ key: `above_${periods[periods.length - 1]}`, desc: true }}
        empty={loading ? 'Loading…' : 'No sectors with enough stocks. Lower "Min stocks" or check the universe has daily data.'}
        dense
      />
    </Card>
  );
}

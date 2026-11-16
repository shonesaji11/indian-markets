import { useState } from 'react';
import { useIngest, useSyncInstruments } from '@/api/queries';
import { INTERVALS, type Instrument, type Interval } from '@/api/types';
import { Button, Card, Chip, ErrorMessage, Field, Select, TextInput } from '@/components/ui';
import { InstrumentPicker } from '@/features/instruments/InstrumentPicker';

/** Queue historical downloads for a basket of instruments. */
export function IngestPanel() {
  const [basket, setBasket] = useState<Instrument[]>([]);
  const [interval, setTimeframe] = useState<Interval>('1d');
  const [start, setStart] = useState('');
  const ingest = useIngest();
  const sync = useSyncInstruments();

  const add = (i: Instrument) =>
    setBasket((b) => (b.some((x) => x.instrument_id === i.instrument_id) ? b : [...b, i]));

  return (
    <Card
      title="Fetch history"
      subtitle="Leave start empty to fetch incrementally from the last stored bar (or the default lookback)."
      actions={
        <Button size="sm" loading={sync.isPending} onClick={() => sync.mutate()}>
          {sync.data ? `Synced ${sync.data.instruments.toLocaleString()}` : 'Sync instrument list'}
        </Button>
      }
    >
      <div className="ui-row">
        <Field label="Add instrument">
          <InstrumentPicker onChange={add} />
        </Field>
        <Field label="Interval">
          <Select value={interval} options={INTERVALS} onChange={setTimeframe} />
        </Field>
        <Field label="Start (optional)">
          <TextInput type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Button
          variant="primary"
          disabled={basket.length === 0}
          loading={ingest.isPending}
          onClick={() =>
            ingest.mutate({
              instrument_ids: basket.map((i) => i.instrument_id),
              interval,
              start: start ? `${start}T00:00:00` : undefined,
            })
          }
        >
          Fetch {basket.length || ''}
        </Button>
      </div>
      {basket.length > 0 && (
        <div className="ui-row" style={{ marginTop: 12 }}>
          {basket.map((i) => (
            <Chip key={i.instrument_id} onRemove={() => setBasket((b) => b.filter((x) => x !== i))}>
              {i.exchange}:{i.symbol}
            </Chip>
          ))}
        </div>
      )}
      <ErrorMessage error={ingest.error ?? sync.error} />
    </Card>
  );
}

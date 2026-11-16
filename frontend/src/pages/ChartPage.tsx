import { useMemo } from 'react';
import { useCalcSeriesList, useCandles, useIngest } from '@/api/queries';
import { INTERVALS, type Interval } from '@/api/types';
import { PriceChart, toOhlc, type ChartSeries, type ValuePoint } from '@/components/charts';
import { Button, Card, Chip, Delta, EmptyState, ErrorMessage, Field, Select } from '@/components/ui';
import { addIndicator, indicatorsCodec, type ActiveIndicator } from '@/features/indicators/activeIndicators';
import { IndicatorPicker } from '@/features/indicators/IndicatorPicker';
import { isOverlay, paramsLabel, toChartSeries } from '@/features/indicators/toChartSeries';
import { InstrumentPicker } from '@/features/instruments/InstrumentPicker';
import { useThemeVersion } from '@/hooks/useTheme';
import { useUrlState } from '@/hooks/useUrlState';
import { cssVar, fmt } from '@/lib/format';
import { toChartTime } from '@/lib/time';

const slotColor = (slot: number) => cssVar(`--series-${slot}`);

const DEFAULT_INDICATORS: ActiveIndicator[] = [{ name: 'sma', params: { period: 50, source: 'close' }, slot: 2 }];

export function ChartPage() {
  const [instrumentParam, setInstrument] = useUrlState('instrument');
  const instrumentId = instrumentParam ? Number(instrumentParam) : undefined;
  const [intervalParam, setInterval] = useUrlState('interval', '1d');
  const interval = intervalParam as Interval;

  const themeVersion = useThemeVersion();
  const [indicators, setIndicators] = useUrlState('ind', DEFAULT_INDICATORS, indicatorsCodec);
  const candles = useCandles(instrumentId, interval);
  const calcs = useCalcSeriesList(instrumentId, interval, indicators);
  const ingest = useIngest();

  const { ohlc, volume } = useMemo(() => {
    const rows = candles.data?.candles ?? [];
    const up = cssVar('--up');
    const down = cssVar('--down');
    const ohlc = toOhlc(rows);
    const volume: ValuePoint[] = rows.map((c) => ({
      time: toChartTime(c.ts),
      value: c.volume,
      color: `${c.close >= c.open ? up : down}55`,
    }));
    return { ohlc, volume };
  }, [candles.data, themeVersion]);

  // useQueries returns a new array every render; key the memo on when each result last changed.
  const calcVersion = calcs.map((q) => q.dataUpdatedAt).join(',');
  const series = useMemo(() => {
    let nextPane = 1;
    const out: ChartSeries[] = [];
    indicators.forEach((ind, i) => {
      const data = calcs[i]?.data;
      if (data) out.push(...toChartSeries(data, ind.slot, isOverlay(ind.name) ? 0 : nextPane++, slotColor));
    });
    return out;
  }, [indicators, calcVersion, themeVersion]); // calcs is read through calcVersion

  const instrument = candles.data?.instrument;
  const bars = candles.data?.candles ?? [];
  const last = bars[bars.length - 1];
  const prev = bars[bars.length - 2];
  const change = last && prev ? last.close - prev.close : null;
  const calcError = calcs.find((q) => q.error)?.error;

  return (
    <div className="page">
      <Card>
        <div className="ui-row">
          <Field label="Instrument">
            <InstrumentPicker value={instrument} onChange={(i) => setInstrument(String(i.instrument_id))} />
          </Field>
          <Field label="Interval">
            <Select value={interval} options={INTERVALS} onChange={setInterval} />
          </Field>
          <div style={{ flex: 1 }} />
          <IndicatorPicker onAdd={(sel) => setIndicators(addIndicator(indicators, sel))} />
        </div>
        {indicators.length > 0 && (
          <div className="ui-row" style={{ marginTop: 12 }}>
            {indicators.map((ind, i) => (
              <span key={ind.slot} title={calcs[i]?.data ? `calc_id ${calcs[i].data!.calc_id}` : undefined}>
                <Chip
                  color={`var(--series-${ind.slot})`}
                  onRemove={() => setIndicators(indicators.filter((x) => x.slot !== ind.slot))}
                >
                  {ind.name}({paramsLabel(ind.params)})
                  {calcs[i]?.data && <span className="muted">v{calcs[i].data!.version}</span>}
                </Chip>
              </span>
            ))}
          </div>
        )}
      </Card>

      <Card
        title={
          instrument ? (
            <span className="ui-row" style={{ alignItems: 'baseline', gap: 10 }}>
              <span>
                {instrument.exchange}:{instrument.symbol}
              </span>
              {last && <span className="num" style={{ fontSize: 'var(--text-lg)' }}>{fmt.price(last.close)}</span>}
              {change != null && prev && (
                <Delta value={change / prev.close} format={fmt.pctAbs} arrow />
              )}
            </span>
          ) : (
            'Chart'
          )
        }
        subtitle={
          instrument
            ? `${instrument.name ?? ''} · ${ohlc.length.toLocaleString()} bars · ${interval}${last ? ` · last ${fmt.longDate(last.ts)}` : ''}`
            : undefined
        }
        actions={
          instrument && (
            <Button
              size="sm"
              loading={ingest.isPending}
              onClick={() => ingest.mutate({ instrument_ids: [instrument.instrument_id], interval })}
            >
              Fetch latest
            </Button>
          )
        }
        divided
        flush
      >
        <ErrorMessage error={candles.error ?? calcError} />
        {instrumentId === undefined ? (
          <EmptyState>Pick an instrument to chart.</EmptyState>
        ) : ohlc.length === 0 && !candles.isLoading ? (
          <EmptyState>
            No {interval} candles stored for this instrument yet. Use “Fetch latest” to download history.
          </EmptyState>
        ) : (
          <div style={{ padding: '8px 4px 4px' }}>
            <PriceChart candles={ohlc} volume={volume} series={series} showTime={interval !== '1d'} />
          </div>
        )}
      </Card>
    </div>
  );
}

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useCalcSeriesList, useCandles, useIngest } from '@/api/queries';
import { INTERVALS, type Interval } from '@/api/types';
import {
  PriceChart,
  toOhlc,
  type ChartSeries,
  type MeasuredRange,
  type RangeKind,
  type ValuePoint,
} from '@/components/charts';
import { Button, Card, Chip, Delta, EmptyState, ErrorMessage, Field, Select, SwatchPicker } from '@/components/ui';
import {
  addIndicator,
  indicatorsCodec,
  recolorIndicator,
  type ActiveIndicator,
} from '@/features/indicators/activeIndicators';
import { IndicatorPicker } from '@/features/indicators/IndicatorPicker';
import { SERIES_SLOTS, isOverlay, paramsLabel, toChartSeries } from '@/features/indicators/toChartSeries';
import { loadChartList } from '@/features/charts/chartList';
import { RelatedList, type SidePaneProps } from '@/features/charts/RelatedList';
import { InstrumentPicker } from '@/features/instruments/InstrumentPicker';
import { WatchlistStar } from '@/features/watchlists/WatchlistStar';
import { useThemeVersion } from '@/hooks/useTheme';
import { useUrlState } from '@/hooks/useUrlState';
import { cssVar, fmt } from '@/lib/format';
import { loadSetting, saveSetting } from '@/lib/storage';
import { toChartTime } from '@/lib/time';

const slotColor = (slot: number) => cssVar(`--series-${slot}`);
/** Slot n (1-based) is index n - 1 here. */
const SLOT_COLORS = Array.from({ length: SERIES_SLOTS }, (_, i) => `var(--series-${i + 1})`);

const DEFAULT_INDICATORS: ActiveIndicator[] = [{ name: 'sma', params: { period: 50, source: 'close' }, slot: 2 }];
/** The last indicator set you chose; used for any chart whose link doesn't carry its own. */
const INDICATORS_KEY = 'markets.chart.indicators';
/** Whether the side list is shown (remembered per browser). */
const LIST_OPEN_KEY = 'markets.chart.listOpen';
/** Fill the window below the header and toolbar, but never shorter than a usable chart. */
const CHART_HEIGHT = 'max(420px, calc(100vh - 250px))';

interface ChartPageProps {
  /** Replaces the list the chart was opened from (Watchlists tab). */
  sidePane?: (props: SidePaneProps) => ReactNode;
  /** Shown first in the toolbar (the Watchlists tab's Chart | Performance switch). */
  toolbarStart?: ReactNode;
  /** Replaces the toolbar and the chart, keeping the side pane (the Watchlists tab's Performance view). */
  main?: ReactNode;
}

/** The chart, with the list it was opened from beside it. */
export function ChartPage({ sidePane, toolbarStart, main }: ChartPageProps) {
  const [instrumentParam, setInstrument] = useUrlState('instrument');
  const instrumentId = instrumentParam ? Number(instrumentParam) : undefined;
  const [intervalParam, setInterval] = useUrlState('interval', '1d');
  const interval = intervalParam as Interval;

  const themeVersion = useThemeVersion();
  // Read on every render (cheap) so a link opened from within the chart page also gets the latest set.
  const savedRaw = loadSetting(INDICATORS_KEY);
  const savedIndicators = useMemo(
    () => (savedRaw == null ? DEFAULT_INDICATORS : indicatorsCodec.parse(savedRaw)),
    [savedRaw],
  );
  const [indicators, setUrlIndicators] = useUrlState('ind', savedIndicators, indicatorsCodec);
  const setIndicators = (next: ActiveIndicator[]) => {
    saveSetting(INDICATORS_KEY, indicatorsCodec.format(next));
    setUrlIndicators(next);
  };
  // The list the chart was opened from (a scan, a sector...), if any.
  const [listId] = useUrlState('list');
  const list = useMemo(() => loadChartList(listId), [listId]);
  const [listOpen, setListOpenState] = useState(() => loadSetting(LIST_OPEN_KEY) !== '0');
  const setListOpen = (open: boolean) => {
    saveSetting(LIST_OPEN_KEY, open ? null : '0');
    setListOpenState(open);
  };
  // Price/date ranges measured on the chart; not saved, cleared on a new stock or interval and by Esc.
  const [rangeTool, setRangeTool] = useState<RangeKind | null>(null);
  const [ranges, setRanges] = useState<MeasuredRange[]>([]);
  useEffect(() => {
    setRangeTool(null);
    setRanges([]);
  }, [instrumentId, interval]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && e.target.closest('input, textarea, select');
      if (e.key !== 'Escape' || e.defaultPrevented || typing) return; // PriceChart cancels an unfinished range first
      setRangeTool(null);
      setRanges([]);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const toggleTool = (kind: RangeKind) => setRangeTool((t) => (t === kind ? null : kind));
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
    <div className="page page--wide">
      {!main && <Card>
        <div className="ui-row">
          {toolbarStart && <span style={{ alignSelf: 'flex-end' }}>{toolbarStart}</span>}
          <Field label="Instrument">
            <InstrumentPicker value={instrument} onChange={(i) => setInstrument(String(i.instrument_id))} />
          </Field>
          <Field label="Interval">
            <Select value={interval} options={INTERVALS} onChange={setInterval} />
          </Field>
          {indicators.map((ind, i) => (
            <span
              key={ind.slot}
              style={{ alignSelf: 'flex-end' }}
              title={calcs[i]?.data ? `calc_id ${calcs[i].data!.calc_id}` : undefined}
            >
              <Chip
                colorControl={
                  <SwatchPicker
                    colors={SLOT_COLORS}
                    value={ind.slot - 1}
                    taken={indicators.filter((x) => x !== ind).map((x) => x.slot - 1)}
                    onChange={(c) => setIndicators(recolorIndicator(indicators, ind.slot, c + 1))}
                  />
                }
                onRemove={() => setIndicators(indicators.filter((x) => x.slot !== ind.slot))}
              >
                {ind.name}({paramsLabel(ind.params)})
                {calcs[i]?.data && <span className="muted">v{calcs[i].data!.version}</span>}
              </Chip>
            </span>
          ))}
          <div style={{ flex: 1 }} />
          <IndicatorPicker onAdd={(sel) => setIndicators(addIndicator(indicators, sel))} />
        </div>
      </Card>}

      <div
        className={`chart-layout${!list && !sidePane ? ' chart-layout--single' : !listOpen ? ' chart-layout--closed' : sidePane ? ' chart-layout--wide' : ''}`}
      >
        {main ?? <Card
          title={
            instrument ? (
              <span className="ui-row" style={{ alignItems: 'baseline', gap: 10 }}>
                <span>
                  {instrument.exchange}:{instrument.symbol}
                </span>
                {last && (
                  <span className="num" style={{ fontSize: 'var(--text-lg)' }}>
                    {fmt.price(last.close)}
                  </span>
                )}
                {change != null && prev && <Delta value={change / prev.close} format={fmt.pctAbs} arrow />}
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
              <>
                <WatchlistStar instrumentId={instrument.instrument_id} />
                {ohlc.length > 0 && (
                  <>
                    <Button
                      size="sm"
                      icon
                      aria-pressed={rangeTool === 'price'}
                      title="Price range: click two points"
                      onClick={() => toggleTool('price')}
                    >
                      ↕
                    </Button>
                    <Button
                      size="sm"
                      icon
                      aria-pressed={rangeTool === 'date'}
                      title="Date range: click two points"
                      onClick={() => toggleTool('date')}
                    >
                      ↔
                    </Button>
                    <Button size="sm" icon title="Clear ranges (Esc)" onClick={() => setRanges([])}>
                      ✕
                    </Button>
                  </>
                )}
                <Button
                  size="sm"
                  loading={ingest.isPending}
                  onClick={() =>
                    ingest.mutate({
                      instrument_ids: [instrument.instrument_id],
                      interval,
                    })
                  }
                >
                  Fetch latest
                </Button>
              </>
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
              <PriceChart
                candles={ohlc}
                volume={volume}
                series={series}
                height={CHART_HEIGHT}
                showTime={interval !== '1d'}
                ranges={ranges}
                rangeTool={rangeTool}
                onRangeAdd={(r) => {
                  setRanges((rs) => [...rs, r]);
                  setRangeTool(null);
                }}
              />
            </div>
          )}
        </Card>}
        {sidePane
          ? sidePane({
              current: instrumentId,
              onSelect: (id) => setInstrument(String(id)),
              open: listOpen,
              onOpenChange: setListOpen,
            })
          : list && (
              <RelatedList
                list={list}
                current={instrumentId}
                onSelect={(id) => setInstrument(String(id))}
                open={listOpen}
                onOpenChange={setListOpen}
              />
            )}
      </div>
    </div>
  );
}

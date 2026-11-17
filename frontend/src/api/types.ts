// Shapes returned by the backend (backend/src/markets/api). Timestamps are naive IST ISO strings.

export const INTERVALS = ['1m', '3m', '5m', '10m', '15m', '30m', '1h', '1d'] as const;
export type Interval = (typeof INTERVALS)[number];

export interface Instrument {
  instrument_id: number;
  exchange: string;
  symbol: string;
  name: string | null;
  instrument_type: string | null;
  lot_size: number | null;
  tick_size: number | null;
  expiry: string | null;
  strike: number | null;
}

export interface Candle {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandleSeries {
  instrument: Instrument;
  interval: Interval;
  candles: Candle[];
}

export type ParamValue = string | number | boolean;

export interface IndicatorInfo {
  name: string;
  version: number;
  outputs: string[];
  params: Record<string, ParamValue>;
  description: string;
}

export type CalcPoint = { ts: string } & Record<string, number | string | null>;

export interface CalcSeries {
  calc_id: string;
  name: string;
  version: number;
  params: Record<string, ParamValue>;
  outputs: string[];
  points: CalcPoint[];
}

export interface CalcDefinition {
  calc_id: string;
  name: string;
  version: number;
  params: Record<string, ParamValue>;
  outputs: string[];
  code_hash: string;
  created_at: string;
}

export interface CoverageRow {
  instrument_id: number;
  exchange: string;
  symbol: string;
  name: string | null;
  timeframe: Interval;
  bars: number;
  first_ts: string;
  last_ts: string;
  last_ingested_at: string;
}

export interface IngestRun {
  run_id: string;
  provider: string;
  instrument_id: number;
  exchange: string | null;
  symbol: string | null;
  timeframe: Interval;
  window_start: string;
  window_end: string;
  status: 'running' | 'ok' | 'error';
  rows_written: number | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface MarketRow {
  instrument_id: number;
  exchange: string;
  symbol: string;
  name: string | null;
  industry?: string | null;
  ts: string;
  close: number;
  change: number | null;
  pct_change: number | null;
  gap_pct: number | null;
  volume: number;
  relative_volume: number | null;
  high_52w: number | null;
  low_52w: number | null;
  from_high_52w: number | null;
  spark?: { ts: string; close: number }[];
}

export interface Breadth {
  total: number;
  advances: number;
  declines: number;
  unchanged: number;
  above_sma_50: number | null;
  above_sma_200: number | null;
  new_highs: number;
  new_lows: number;
}

export type ScanMetric = 'pct_change' | 'relative_volume' | 'gap_pct' | 'from_high_52w';

export interface ScanResult {
  name: string;
  version: number;
  title: string;
  description: string;
  metric: ScanMetric;
  rows: MarketRow[];
}

export interface MarketOverview {
  as_of: string | null;
  universe: { id: string; members: number; priced: number };
  benchmarks: MarketRow[];
  sectors: MarketRow[];
  breadth: Breadth;
  scans: ScanResult[];
}

export interface Watchlist {
  watchlist_id: string;
  name: string;
  description: string | null;
  source: string | null;
  members: number;
  updated_at: string;
}

// --- Custom scans (backend engine/screener.py) ---

export type ScanOp = 'gt' | 'gte' | 'lt' | 'lte' | 'crosses_above' | 'crosses_below';

export type ScanOperand =
  | { type: 'field'; field: string }
  | { type: 'indicator'; name: string; params: Record<string, ParamValue>; output: string };

/** Right-hand side: an operand or a number (percent fields take percentages, e.g. 2.5 = 2.5%). */
export type ScanRight = ScanOperand | { type: 'value'; value: number | null };

export interface ScanCondition {
  type: 'condition';
  left: ScanOperand;
  op: ScanOp;
  right: ScanRight;
}

export interface ScanGroup {
  type: 'group';
  match: 'all' | 'any';
  items: (ScanCondition | ScanGroup)[];
}

export interface ScanField {
  name: string;
  label: string;
  percent: boolean;
}

export interface ScanDefinition {
  filter: ScanGroup;
  universe: string;
  include_indices: boolean;
}

export interface ScanRequest extends ScanDefinition {
  as_of?: string;
  /** Limit to one sector (NSE industry tag, or 'Unclassified'). */
  industry?: string;
  /** Extra operands to compute and return as columns, without filtering on them. */
  columns?: ScanOperand[];
}

export interface ScanColumn {
  key: string;
  label: string;
  percent: boolean;
}

export type ScanRow = MarketRow & { instrument_type: string } & Record<string, unknown>;

export interface ScanRunResult {
  as_of: string | null;
  /** Bar size every condition is evaluated on (currently always '1d'). */
  timeframe: Interval;
  universe: { id: string; members: number; priced: number; matched: number };
  columns: ScanColumn[];
  rows: ScanRow[];
}

export interface ScanPerformanceRequest {
  instrument_ids: number[];
  /** The scan's session (ISO date): the basket is bought at the next session's open. */
  start: string;
  /** Last session to measure to (ISO date); default latest stored. */
  end?: string;
}

export interface PerformancePoint {
  ts: string;
  /** Change since the start close, as a fraction. */
  value: number | null;
}

export interface ScanPerformance {
  start: string | null;
  end: string | null;
  /** Sessions after the start. */
  sessions: number;
  total: number;
  /** Stocks in the basket average (a close on the start session and a bar after it). */
  counted: number;
  /** `entry` = open of the first bar after the pick; null (with change) when not counted. */
  stocks: { instrument_id: number; entry: number | null; close: number | null; change: number | null }[];
  basket: PerformancePoint[];
  benchmark: { label: string; points: PerformancePoint[] } | null;
}

export interface SavedScan {
  scan_id: string;
  name: string;
  definition: ScanDefinition;
  created_at: string;
  updated_at: string;
}

export interface SectorBreadthRow {
  industry: string;
  stocks: number;
  /** Stocks above each SMA, keyed by period ("10", "20"). */
  above: Record<string, number>;
}

export interface SectorBreadth {
  as_of: string | null;
  universe: string;
  periods: number[];
  sectors: SectorBreadthRow[];
}

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

/** One of your own lists; `member_ids` in the order you added them. */
export interface MyWatchlist {
  watchlist_id: string;
  name: string;
  member_ids: number[];
}

/** A stock in one of your lists with its last stored daily bar (all null if none stored yet). */
export interface WatchlistQuote {
  instrument_id: number;
  exchange: string;
  symbol: string;
  name: string | null;
  instrument_type: string | null;
  ts: string | null;
  close: number | null;
  /** Fraction vs the previous bar. */
  pct_change: number | null;
}

// --- Live quotes (backend pipelines/live.py, routers/live.py) ---

/** Latest streamed quote. `ts` is the exchange's time (naive IST), possibly from an earlier day. */
export interface LiveQuote {
  instrument_id: number;
  ts: string;
  ltp: number;
  open: number | null;
  high: number | null;
  low: number | null;
  /** The previous session's close, as the stream reports it (already adjusted on split/bonus days). */
  prev_close: number | null;
  /** Day's volume so far (0 for indices). */
  volume: number | null;
}

export interface LiveStatus {
  connected: boolean;
  /** 09:15–15:30 IST on a weekday (holidays included: no quotes come then). */
  session_open: boolean;
  /** Today's date in IST, "YYYY-MM-DD". */
  today: string;
  /** Exchange time of the newest quote received. */
  last_tick: string | null;
  /** When the feed dropped (or first failed to connect); null while connected. */
  lost_at: string | null;
}

export interface LiveQuotes {
  status: LiveStatus;
  quotes: LiveQuote[];
}

// --- Price alerts (backend pipelines/alerts.py, routers/alerts.py) ---

export type AlertDirection = 'above' | 'below';

export interface PriceAlert {
  alert_id: string;
  instrument_id: number;
  exchange: string;
  symbol: string;
  instrument_type: string | null;
  direction: AlertDirection;
  price: number;
  note: string | null;
  created_at: string;
  /** Null while active. */
  triggered_at: string | null;
  triggered_price: number | null;
  /** Telegram: sent / failed / off (not set up); null until tried. */
  notified: 'sent' | 'failed' | 'off' | null;
  notify_error: string | null;
  /** Last stored daily close (for "now" when there's no live price). */
  close: number | null;
}

export interface AlertsResponse {
  /** Active first (oldest first), then fired (newest first). */
  alerts: PriceAlert[];
  telegram: boolean;
  live: LiveStatus;
}

export interface AlertInput {
  direction: AlertDirection;
  price: number;
  note: string | null;
}

// --- Custom scans (backend engine/screener.py) ---

export type ScanOp = 'gt' | 'gte' | 'lt' | 'lte' | 'crosses_above' | 'crosses_below';

/** Read an operand N trading sessions back: d = 1, w = 5, m = 21 sessions (up to 252). */
export interface ScanAgo {
  n: number;
  unit: 'd' | 'w' | 'm';
}

export type ScanOperand = (
  | { type: 'field'; field: string }
  | { type: 'indicator'; name: string; params: Record<string, ParamValue>; output: string }
) & { ago?: ScanAgo };

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

/** Near-high reference: 52-week high, or all-time high (since listing or the first stored bar). */
export type HighBasis = '52w' | 'ath';

/** "Within `pct`% of the `basis` high". */
export interface NearHigh {
  pct: number;
  basis: HighBasis;
}

export interface SectorBreadthRow {
  industry: string;
  stocks: number;
  /** Stocks above each SMA, keyed by period ("10", "20"). */
  above: Record<string, number>;
  /** Stocks with a reference high, and how many closed within near_pct% of it. */
  near_high: { stocks: number; near: number } | null;
}

export interface SectorBreadth {
  as_of: string | null;
  universe: string;
  periods: number[];
  near_pct: number;
  near_basis: HighBasis;
  sectors: SectorBreadthRow[];
}

/** What the rotation view ranks sectors by: share above the MA, or share near their high. */
export type RankBy = 'ma' | 'near_high';

/** One sector's average daily rank by share of stocks above the SMA (1 = best), now vs earlier. */
export interface SectorRotationRow {
  industry: string;
  /** Stocks priced on the latest session. */
  stocks: number;
  rank_now: number;
  /** Null when the sector wasn't ranked in the earlier window (too few stocks then, or new). */
  rank_then: number | null;
  /** rank_then − rank_now: positive = climbing towards rank 1. */
  rank_change: number | null;
  /** Average share above the SMA over each window (0..1). */
  share_now: number;
  share_then: number | null;
}

export interface SectorRotation {
  as_of: string | null;
  universe: string;
  period: number;
  ago: ScanAgo;
  rank_by: RankBy;
  near_pct: number;
  near_basis: HighBasis;
  /** Sessions averaged on each side. */
  window: number;
  min_stocks: number;
  /** First and last session of each window. */
  windows: { now: [string, string]; then: [string, string] } | null;
  /** Sectors left out for having fewer than min_stocks stocks. */
  hidden: number;
  sectors: SectorRotationRow[];
}

/** One stock on the big-movers list (GET /movers). move/hit: the next session, null until its bar exists. */
export interface MoverRow {
  instrument_id: number;
  symbol: string;
  name: string | null;
  /** Model probability of a big close-vs-open move on the next session (0-1). */
  probability: number;
  atr_pct: number | null;
  /** Close on as_of and its change from the close before. */
  close: number | null;
  change: number | null;
  /** Next session's close / open - 1. */
  move: number | null;
  hit: boolean | null;
}

/** The big-movers list scored after the close of as_of (mirrors MoverService.picks). */
export interface MoverList {
  model_version: string;
  cutoff: number;
  default_cutoff: number;
  /** |move| that counts as big (0.04). */
  big_move: number;
  as_of: string | null;
  /** False when no list was scored for as_of (or none at all, with as_of null). */
  scored: boolean;
  rows: MoverRow[];
  universe?: number;
  with_bar?: number;
  stocks?: number;
  /** The session after as_of once it has bars, else null; assumed_next_session = next weekday. */
  next_session?: string | null;
  assumed_next_session?: string;
  top_probability?: number | null;
  listed?: number;
  listed_with_bar?: number;
  hits?: number;
  /** Every scored stock: how many traded on the next session, and how many of those moved big. */
  all_with_bar?: number;
  all_hits?: number;
}

/** One scored day (GET /movers/days), newest first. */
export interface MoverDay {
  as_of: string;
  next_session: string | null;
  listed: number;
  with_bar: number;
  hits: number;
}

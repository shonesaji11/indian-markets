-- Per-instrument daily signals as of any date: one row per instrument (its last bar on or
-- before `as_of`). A table macro rather than a view so the date filter is applied before
-- the window functions run, which keeps "as of" queries fast across hundreds of stocks.
-- Only bars up to `as_of` are read, so results are point-in-time by construction.
--
-- Differences from v_daily_stats_v1: average volume excludes the current bar (so a volume
-- spike is compared with the days before it), plus gap, SMA 50/200 and distance from high.
--
-- Usage: SELECT * FROM daily_signals_v1(TIMESTAMP '2024-03-15 23:59:59');
-- To change the logic, add daily_signals_v2 in a new migration; keep v1 unchanged.

CREATE MACRO daily_signals_v1(as_of) AS TABLE
WITH recent AS (
    SELECT instrument_id, ts, open, high, low, close, volume
    FROM candles
    WHERE timeframe = '1d'
      AND ts <= as_of
      AND ts > as_of - INTERVAL 450 DAY          -- >= 252 trading days of history
),
w AS (
    SELECT
        *,
        lag(close)   OVER by_ts          AS prev_close,
        max(high)    OVER last_252       AS high_52w,
        min(low)     OVER last_252       AS low_52w,
        count(*)     OVER last_252       AS bars_252,
        avg(volume)  OVER prior_20       AS avg_volume_20d,
        avg(close)   OVER last_50        AS sma_50_raw,
        count(*)     OVER last_50        AS bars_50,
        avg(close)   OVER last_200       AS sma_200_raw,
        count(*)     OVER last_200       AS bars_200,
        row_number() OVER (PARTITION BY instrument_id ORDER BY ts DESC) AS recency
    FROM recent
    WINDOW
        by_ts    AS (PARTITION BY instrument_id ORDER BY ts),
        last_252 AS (PARTITION BY instrument_id ORDER BY ts ROWS BETWEEN 251 PRECEDING AND CURRENT ROW),
        prior_20 AS (PARTITION BY instrument_id ORDER BY ts ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING),
        last_50  AS (PARTITION BY instrument_id ORDER BY ts ROWS BETWEEN 49 PRECEDING AND CURRENT ROW),
        last_200 AS (PARTITION BY instrument_id ORDER BY ts ROWS BETWEEN 199 PRECEDING AND CURRENT ROW)
)
SELECT
    w.instrument_id,
    i.exchange,
    i.symbol,
    i.name,
    i.instrument_type,
    w.ts,
    w.open, w.high, w.low, w.close, w.volume,
    w.prev_close,
    w.close - w.prev_close                              AS change,
    w.close / nullif(w.prev_close, 0) - 1               AS pct_change,
    w.open  / nullif(w.prev_close, 0) - 1               AS gap_pct,
    w.high_52w,
    w.low_52w,
    w.close / nullif(w.high_52w, 0) - 1                 AS from_high_52w,
    w.bars_252,
    w.avg_volume_20d,
    w.volume / nullif(w.avg_volume_20d, 0)              AS relative_volume,
    CASE WHEN w.bars_50  = 50  THEN w.sma_50_raw  END   AS sma_50,
    CASE WHEN w.bars_200 = 200 THEN w.sma_200_raw END   AS sma_200
FROM w
JOIN instruments i USING (instrument_id)
WHERE w.recency = 1;

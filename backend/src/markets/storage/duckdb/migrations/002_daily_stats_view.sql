-- SQL-side computations live in versioned views. Each row uses only rows at or before
-- its own ts, so filtering on a past date gives the point-in-time answer, e.g. a
-- 52-week-high scan as of 2024-03-15:
--   SELECT symbol, close FROM v_daily_stats_v1
--   WHERE ts = '2024-03-15' AND close >= high_52w;
-- To change the logic, add v_daily_stats_v2 in a new migration; keep v1 unchanged.

CREATE VIEW v_daily_stats_v1 AS
SELECT
    c.instrument_id,
    i.exchange,
    i.symbol,
    c.ts,
    c.open, c.high, c.low, c.close, c.volume,
    lag(c.close) OVER w                                      AS prev_close,
    c.close / nullif(lag(c.close) OVER w, 0) - 1             AS pct_change,
    max(c.high)   OVER w252                                  AS high_52w,
    min(c.low)    OVER w252                                  AS low_52w,
    avg(c.volume) OVER w20                                   AS avg_volume_20d,
    c.volume / nullif(avg(c.volume) OVER w20, 0)             AS relative_volume,
    count(*)      OVER w252                                  AS bars_in_52w
FROM candles c
JOIN instruments i USING (instrument_id)
WHERE c.timeframe = '1d'
WINDOW
    w    AS (PARTITION BY c.instrument_id ORDER BY c.ts),
    w20  AS (PARTITION BY c.instrument_id ORDER BY c.ts ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
    w252 AS (PARTITION BY c.instrument_id ORDER BY c.ts ROWS BETWEEN 251 PRECEDING AND CURRENT ROW);

-- Daily sector breadth: per trading day, universe, sector (NSE industry tag) and MA period,
-- how many stocks were priced and how many closed above their simple moving average.
-- Filled by DuckBreadthRepository.store (nightly for recent days, `markets breadth --backfill` for
-- history, and on first read of a day). Basis for "which sectors are gaining breadth" over time.
CREATE TABLE sector_breadth (
    ts          TIMESTAMP NOT NULL,
    universe    VARCHAR   NOT NULL,           -- watchlist id, or 'all' = every stock with daily data
    industry    VARCHAR   NOT NULL,           -- 'Unclassified' when the stock has no industry tag
    ma_period   INTEGER   NOT NULL,
    stocks      INTEGER   NOT NULL,
    above       INTEGER   NOT NULL,
    computed_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (ts, universe, industry, ma_period)
);

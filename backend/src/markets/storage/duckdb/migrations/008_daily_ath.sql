-- Each instrument's highest daily high up to and including each of its daily bars: its "all-time
-- high" so far, i.e. since its first stored bar (history starts Nov 2016 for older stocks).
-- Derived from candles and kept current per instrument by AthService (pipelines/highs.py): nightly,
-- before every read, and `markets highs --rebuild`. Zero/NaN highs are skipped.
CREATE TABLE daily_ath (
    instrument_id INTEGER   NOT NULL,
    ts            TIMESTAMP NOT NULL,
    ath           DOUBLE,                 -- NULL until the instrument has a valid (positive) high
    PRIMARY KEY (instrument_id, ts)
);

-- Refresh state of derived tables: e.g. the newest candles.ingested_at already applied and the
-- logic version it was applied with ('ath_watermark', 'ath_version').
CREATE TABLE derived_state (
    key        VARCHAR   PRIMARY KEY,
    value      VARCHAR   NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- Data-quality issues found by engine/data_quality.py checks, run after every nightly update
-- (pipelines/data_quality.py). One row per issue; a recurring issue updates its row.
CREATE TABLE dq_issues (
    issue_id      VARCHAR   PRIMARY KEY,     -- check:instrument_id:start date, stable across runs
    check_name    VARCHAR   NOT NULL,        -- gap | bad_bar | jump | stale | short_history | failed_download
    instrument_id INTEGER   NOT NULL,
    start_ts      TIMESTAMP,
    end_ts        TIMESTAMP,
    detail        VARCHAR,
    status        VARCHAR   NOT NULL,        -- open | resolved (re-check passed) | accepted (known, not flagged)
    note          VARCHAR,                   -- why it was accepted
    first_seen    TIMESTAMP NOT NULL,
    last_seen     TIMESTAMP NOT NULL,
    seen_count    INTEGER   NOT NULL,
    resolved_at   TIMESTAMP
);

-- Run state: the newest candles.ingested_at already checked, and the check version it was checked with.
CREATE TABLE dq_state (
    key        VARCHAR   PRIMARY KEY,
    value      VARCHAR   NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- Named instrument lists: index universes (Nifty 500), benchmarks, your own picks.
CREATE TABLE watchlists (
    watchlist_id VARCHAR PRIMARY KEY,           -- slug, e.g. nifty500
    name         VARCHAR   NOT NULL,
    description  VARCHAR,
    source       VARCHAR,                       -- e.g. nse_index:nifty500, manual
    created_at   TIMESTAMP NOT NULL DEFAULT current_timestamp,
    updated_at   TIMESTAMP NOT NULL DEFAULT current_timestamp
);

-- Membership with history: a row per stint in the list, removed_at IS NULL = current.
-- Index compositions change; keeping past members lets backtests avoid survivorship bias
-- ("what was in the Nifty 500 on 2021-03-01?").
CREATE TABLE watchlist_members (
    watchlist_id  VARCHAR   NOT NULL,
    instrument_id INTEGER   NOT NULL,
    added_at      TIMESTAMP NOT NULL,
    removed_at    TIMESTAMP
);

-- Free-form classifications per instrument, e.g. key 'industry' from NSE index files.
CREATE TABLE instrument_tags (
    instrument_id INTEGER   NOT NULL,
    key           VARCHAR   NOT NULL,
    value         VARCHAR,
    source        VARCHAR,
    updated_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (instrument_id, key)
);

-- Core tables. Never edit an applied migration: add a new numbered file instead.
-- Relationships are documented rather than enforced with FOREIGN KEY, because DuckDB
-- blocks upserts on rows that are referenced by a foreign key.

CREATE SEQUENCE instrument_id_seq START 1;

-- Provider-independent instrument master.
CREATE TABLE instruments (
    instrument_id   INTEGER PRIMARY KEY DEFAULT nextval('instrument_id_seq'),
    exchange        VARCHAR NOT NULL,          -- NSE, BSE, NFO, MCX ...
    symbol          VARCHAR NOT NULL,          -- trading symbol, e.g. RELIANCE-EQ
    name            VARCHAR,
    instrument_type VARCHAR,                   -- EQ, INDEX, FUTSTK, OPTIDX ...
    lot_size        INTEGER,
    tick_size       DOUBLE,
    expiry          DATE,
    strike          DOUBLE,
    updated_at      TIMESTAMP NOT NULL DEFAULT current_timestamp,
    UNIQUE (exchange, symbol)
);

-- How each provider identifies an instrument (instrument_id -> instruments).
CREATE TABLE instrument_provider_map (
    instrument_id  INTEGER NOT NULL,
    provider       VARCHAR NOT NULL,
    provider_token VARCHAR NOT NULL,
    PRIMARY KEY (instrument_id, provider)
);

-- OHLCV bars. ts is naive IST and marks the bar open.
CREATE TABLE candles (
    instrument_id INTEGER   NOT NULL,
    timeframe     VARCHAR   NOT NULL,          -- 1m, 5m, 1h, 1d ... (core.models.Interval)
    ts            TIMESTAMP NOT NULL,
    open          DOUBLE,
    high          DOUBLE,
    low           DOUBLE,
    close         DOUBLE,
    volume        DOUBLE,
    source        VARCHAR   NOT NULL,          -- provider that supplied the bar
    ingested_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (instrument_id, timeframe, ts)
);

-- Previous versions of bars that a later ingestion overwrote with different values.
-- Lets you reconstruct exactly what the database held at any past moment.
CREATE TABLE candle_revisions (
    instrument_id INTEGER   NOT NULL,
    timeframe     VARCHAR   NOT NULL,
    ts            TIMESTAMP NOT NULL,
    open          DOUBLE,
    high          DOUBLE,
    low           DOUBLE,
    close         DOUBLE,
    volume        DOUBLE,
    source        VARCHAR   NOT NULL,
    ingested_at   TIMESTAMP NOT NULL,          -- when the old value arrived
    superseded_at TIMESTAMP NOT NULL           -- when it was replaced
);

-- Audit trail of every fetch from a provider.
CREATE TABLE ingestion_runs (
    run_id        VARCHAR PRIMARY KEY,
    provider      VARCHAR   NOT NULL,
    instrument_id INTEGER   NOT NULL,
    timeframe     VARCHAR   NOT NULL,
    window_start  TIMESTAMP NOT NULL,
    window_end    TIMESTAMP NOT NULL,
    status        VARCHAR   NOT NULL,          -- running, ok, error
    rows_written  INTEGER,
    error         VARCHAR,
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP
);

-- A calculation is identified by (name, version, params). calc_id is a hash of those,
-- so changing logic (version bump) or params produces a new calc_id and the old
-- results stay queryable side by side.
CREATE TABLE calc_definitions (
    calc_id    VARCHAR PRIMARY KEY,
    name       VARCHAR   NOT NULL,
    version    INTEGER   NOT NULL,
    params     JSON      NOT NULL,
    outputs    VARCHAR[] NOT NULL,
    code_hash  VARCHAR   NOT NULL,             -- hash of the function source at registration
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE calc_runs (
    run_id         VARCHAR PRIMARY KEY,
    calc_id        VARCHAR   NOT NULL,
    instrument_id  INTEGER   NOT NULL,
    timeframe      VARCHAR   NOT NULL,
    data_watermark TIMESTAMP,                  -- newest candles.ingested_at the run saw
    status         VARCHAR   NOT NULL,
    rows_written   INTEGER,
    error          VARCHAR,
    started_at     TIMESTAMP NOT NULL,
    finished_at    TIMESTAMP
);

-- Long format so any calculation with any number of outputs fits one table.
CREATE TABLE calc_values (
    calc_id       VARCHAR   NOT NULL,
    instrument_id INTEGER   NOT NULL,
    timeframe     VARCHAR   NOT NULL,
    ts            TIMESTAMP NOT NULL,
    output        VARCHAR   NOT NULL,
    value         DOUBLE,
    run_id        VARCHAR   NOT NULL,          -- calc_runs row that last wrote this value
    PRIMARY KEY (calc_id, instrument_id, timeframe, ts, output)
);

-- Big-movers watchlist (pipelines/movers.py): every eligible stock's model probability of a >= 4% close-vs-open
-- move on the session after `as_of`, scored after that day's close. The list = probability >= a cutoff, applied
-- when read. What each stock then did is read live from candles, never stored. Derived data: see derived-data.md.
CREATE TABLE mover_scores (
    model_version VARCHAR NOT NULL,  -- model file under src/markets/models/, e.g. co4_eod_v1
    as_of         DATE    NOT NULL,  -- the session whose close the features are known at
    instrument_id INTEGER NOT NULL,
    probability   DOUBLE  NOT NULL,
    atr_pct       DOUBLE,            -- 14-day ATR / close at as_of (shown beside the probability)
    PRIMARY KEY (model_version, as_of, instrument_id)
);

-- One row per scored day: when it was scored, how complete the bars were, and the evening Telegram message.
CREATE TABLE mover_runs (
    model_version VARCHAR   NOT NULL,
    as_of         DATE      NOT NULL,
    scored_at     TIMESTAMP NOT NULL,
    universe      INTEGER   NOT NULL,  -- universe members when scored (all series: they all feed the market features)
    with_bar      INTEGER   NOT NULL,  -- of those, with a bar on as_of
    stocks        INTEGER   NOT NULL,  -- scored: eligible -EQ stocks (other series are never listed)
    notified      VARCHAR,             -- Telegram: sent, failed, off (not set up); null until tried
    notify_error  VARCHAR,
    PRIMARY KEY (model_version, as_of)
);

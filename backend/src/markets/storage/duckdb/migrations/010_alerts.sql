-- Price alerts (pipelines/alerts.py): each fires once, when the live price reaches `price` from the chosen side.
-- Fired alerts are kept (triggered_at set) until deleted by hand. Times are naive IST like everything else.
CREATE TABLE alerts (
    alert_id        VARCHAR   PRIMARY KEY,
    instrument_id   INTEGER   NOT NULL,
    direction       VARCHAR   NOT NULL,  -- above, below
    price           DOUBLE    NOT NULL,
    note            VARCHAR,
    created_at      TIMESTAMP NOT NULL,
    triggered_at    TIMESTAMP,           -- null while active
    triggered_price DOUBLE,
    notified        VARCHAR,             -- Telegram: sent, failed, off (not set up); null until tried
    notify_error    VARCHAR
);

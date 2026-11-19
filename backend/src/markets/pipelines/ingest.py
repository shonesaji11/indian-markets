from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from markets.core.models import DateRange, IngestionResult, Interval
from markets.core.ports import CandleRepository, IngestionLog, InstrumentRepository, MarketDataProvider

log = logging.getLogger(__name__)

# How far back the first fetch for an instrument goes when no start date is given. Intraday: one Angel One
# request's worth (its max days per getCandleData call), so a chart's first visit takes ~2 seconds.
DEFAULT_HISTORY = {
    Interval.D1: timedelta(days=365 * 10),
    Interval.H1: timedelta(days=400),
    Interval.M30: timedelta(days=200),
    Interval.M15: timedelta(days=200),
    Interval.M10: timedelta(days=100),
    Interval.M5: timedelta(days=100),
    Interval.M3: timedelta(days=60),
    Interval.M1: timedelta(days=30),
}


class IngestionService:
    def __init__(self, provider: MarketDataProvider, instruments: InstrumentRepository,
                 candles: CandleRepository, runs: IngestionLog):
        self.provider = provider
        self.instruments = instruments
        self.candles = candles
        self.runs = runs

    def sync_instruments(self, batch_size: int = 50_000) -> int:
        """Refresh the instrument master from the provider."""
        total, batch = 0, []
        for item in self.provider.list_instruments():
            batch.append(item)
            if len(batch) >= batch_size:
                total += self.instruments.upsert_many(batch)
                batch = []
        total += self.instruments.upsert_many(batch)
        return total

    def ingest(self, instrument_id: int, interval: Interval, start: Optional[datetime] = None,
               end: Optional[datetime] = None) -> IngestionResult:
        """Fetch and store candles.

        With no `start`, this is incremental: it re-fetches from the latest stored bar
        (which may have been partial) or, for a new instrument, from DEFAULT_HISTORY ago.
        """
        instrument = self.instruments.get(instrument_id)
        if instrument is None:
            raise KeyError(f"instrument {instrument_id} not found")
        token = self.instruments.provider_token(instrument_id, self.provider.name)
        if token is None:
            raise KeyError(f"{instrument.symbol} has no token for provider '{self.provider.name}'")

        end = end or datetime.now()
        if start is None:
            latest = self.candles.latest_ts(instrument_id, interval)
            start = latest or end - DEFAULT_HISTORY[interval]
        window = DateRange(start, end)

        run_id = self.runs.start(self.provider.name, instrument_id, interval, window)
        try:
            frame = self.provider.fetch_candles(token, instrument.exchange, interval, window)
            rows = self.candles.upsert(instrument_id, interval, frame, source=self.provider.name)
        except Exception as exc:
            log.exception("ingest failed for %s %s", instrument.symbol, interval.value)
            self.runs.finish(run_id, 0, "error", str(exc))
            return IngestionResult(instrument_id, interval, window, 0, "error", str(exc), run_id)
        self.runs.finish(run_id, rows, "ok")
        log.info("ingested %s %s: %d bars written", instrument.symbol, interval.value, rows)
        return IngestionResult(instrument_id, interval, window, rows, "ok", None, run_id)

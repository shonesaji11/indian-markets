"""Interfaces that decouple the layers.

Pipelines and the API are written against these protocols only. Swapping Angel One for
another broker, or DuckDB for Postgres, means writing a new adapter and nothing else.

Candle frames everywhere use the same shape: a DatetimeIndex named `ts` (naive IST) and
float columns open, high, low, close, volume.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional, Protocol, Sequence

import pandas as pd

from markets.core.models import DateRange, Instrument, Interval, ProviderInstrument


class MarketDataProvider(Protocol):
    name: str

    def list_instruments(self) -> Iterable[ProviderInstrument]:
        """Full instrument universe the provider knows about."""
        ...

    def fetch_candles(self, provider_token: str, exchange: str, interval: Interval, window: DateRange) -> pd.DataFrame:
        """Candles for one instrument. The provider handles its own paging and rate limits."""
        ...

    def close(self) -> None:
        """Release the session (log out). Safe to call when never logged in."""
        ...


class Constituent(Protocol):
    symbol: str
    series: str
    company: str
    industry: str


class ConstituentSource(Protocol):
    """Reference data: which stocks make up an index (e.g. NSE's published lists)."""

    def constituents(self, index: str) -> Sequence[Constituent]: ...


class InstrumentRepository(Protocol):
    def upsert_many(self, items: Sequence[ProviderInstrument]) -> int: ...

    def get(self, instrument_id: int) -> Optional[Instrument]: ...

    def find(self, exchange: str, symbol: str) -> Optional[Instrument]: ...

    def search(self, query: str = "", exchange: Optional[str] = None, instrument_type: Optional[str] = None,
               limit: int = 50) -> list[Instrument]: ...

    def provider_token(self, instrument_id: int, provider: str) -> Optional[str]: ...


class CandleRepository(Protocol):
    def upsert(self, instrument_id: int, interval: Interval, candles: pd.DataFrame, source: str) -> int: ...

    def load(self, instrument_id: int, interval: Interval, start: Optional[datetime] = None,
             end: Optional[datetime] = None) -> pd.DataFrame: ...

    def latest_ts(self, instrument_id: int, interval: Interval) -> Optional[datetime]: ...

    def last_ingested_at(self, instrument_id: int, interval: Interval) -> Optional[datetime]: ...

    def coverage(self) -> list[dict[str, Any]]: ...


class IngestionLog(Protocol):
    def start(self, provider: str, instrument_id: int, interval: Interval, window: DateRange) -> str: ...

    def finish(self, run_id: str, rows: int, status: str, error: Optional[str] = None) -> None: ...

    def recent(self, limit: int = 50) -> list[dict[str, Any]]: ...


class CalcRepository(Protocol):
    def ensure_definition(self, calc_id: str, name: str, version: int, params: dict[str, Any],
                          outputs: Sequence[str], code_hash: str) -> None: ...

    def start_run(self, calc_id: str, instrument_id: int, interval: Interval, data_watermark: Optional[datetime]) -> str: ...

    def finish_run(self, run_id: str, rows: int, status: str, error: Optional[str] = None) -> None: ...

    def write_values(self, run_id: str, calc_id: str, instrument_id: int, interval: Interval,
                     values: pd.DataFrame) -> int: ...

    def load_values(self, calc_id: str, instrument_id: int, interval: Interval,
                    start: Optional[datetime] = None, end: Optional[datetime] = None) -> pd.DataFrame: ...

    def definitions(self) -> list[dict[str, Any]]: ...

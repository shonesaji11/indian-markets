"""Interfaces that decouple the layers.

Pipelines and the API are written against these protocols only. Swapping Angel One for
another broker, or DuckDB for Postgres, means writing a new adapter and nothing else.

Candle frames everywhere use the same shape: a DatetimeIndex named `ts` (naive IST) and
float columns open, high, low, close, volume.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Iterable, Optional, Protocol, Sequence

import pandas as pd

from markets.core.models import DateRange, Instrument, Interval, LiveTick, ProviderInstrument


class MarketDataProvider(Protocol):
    """A market data source. The rest of the app looks instruments up by name, so an adapter must
    convert its source's own formats into the ones below. Nothing fails loudly if it doesn't: watchlists,
    the overview, scans and breadth just come up empty.

    `name` is a stable string: it keys each instrument's token in the database.
    """

    name: str

    def list_instruments(self) -> Iterable[ProviderInstrument]:
        """Full instrument universe the provider knows about, each with `provider == self.name`.

        - `exchange` is an uppercase code: "NSE", "BSE" (other segments may be listed too).
        - NSE cash equities are named "<TICKER>-<SERIES>" ("RELIANCE-EQ", "BAJAJ-AUTO-EQ", "XYZ-BE")
          with `instrument_type` "EQ": index constituents from NSE's lists are found as symbol + "-" + series.
        - Indices have `instrument_type` "INDEX", and the ones named in universes.WATCHLISTS are listed
          under exactly those names ("NSE:Nifty 50", "BSE:SENSEX", ...; matched case-insensitively).
        - `provider_token` is a non-empty string, unique within its exchange, that `fetch_candles` accepts.
        """
        ...

    def fetch_candles(self, provider_token: str, exchange: str, interval: Interval, window: DateRange) -> pd.DataFrame:
        """Candles for one instrument, in the shape described at the top of this module: sorted, no
        duplicate timestamps, an empty frame of that shape when there are none. Daily bars are stamped
        00:00 IST on the trading date; intraday bars are labelled by their start (09:15 to 15:29 IST).
        The provider handles its own paging and rate limits, and raises (ideally ProviderError) once its
        own retries are used up."""
        ...

    def last_trade_dates(self, exchange: str, tokens: Sequence[str]) -> dict[str, date]:
        """Date of each instrument's last trade, from live quotes, keyed by the same token strings
        that were passed in. Tokens without a quote are left out."""
        ...

    def close(self) -> None:
        """Release the session (log out). Safe to call when never logged in."""
        ...


class LiveFeed(Protocol):
    """A streaming quote connection (one at a time). Instruments are referred to as (exchange, provider token)
    pairs, the same token `MarketDataProvider.list_instruments` gives. Callbacks run on the feed's own thread."""

    max_subscriptions: int

    def connect(self, on_tick: Callable[[LiveTick], None], on_close: Callable[[], None]) -> None:
        """Open the connection; returns once it is open, raises (ideally ProviderError) if it can't.
        Every quote goes to `on_tick`; `on_close` is called once if the connection drops by itself."""
        ...

    def subscribe(self, refs: Sequence[tuple[str, str]]) -> None:
        """Start streaming these (exchange, token) pairs on the open connection. Each sends its latest
        quote straight away, also outside market hours. Unsupported exchanges are skipped."""
        ...

    def close(self) -> None:
        """Close the connection (no `on_close` call). Safe to call when not connected."""
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

    def equity_tokens(self, exchange: str, series: Sequence[str], provider: str) -> pd.DataFrame: ...


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

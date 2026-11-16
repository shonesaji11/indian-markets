from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional

# Convention: every timestamp in the system is a naive datetime in IST (Asia/Kolkata).
# Providers convert to this on the way in; the UI treats it as exchange-local time.

CANDLE_COLUMNS = ("open", "high", "low", "close", "volume")


class Interval(str, Enum):
    """Our own interval codes. Providers map these to their own vocabulary."""

    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M10 = "10m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    D1 = "1d"

    @property
    def duration(self) -> timedelta:
        return _DURATIONS[self]


_DURATIONS = {
    Interval.M1: timedelta(minutes=1),
    Interval.M3: timedelta(minutes=3),
    Interval.M5: timedelta(minutes=5),
    Interval.M10: timedelta(minutes=10),
    Interval.M15: timedelta(minutes=15),
    Interval.M30: timedelta(minutes=30),
    Interval.H1: timedelta(hours=1),
    Interval.D1: timedelta(days=1),
}


@dataclass(frozen=True)
class Instrument:
    """A tradable instrument, independent of any data provider.

    `instrument_id` is our surrogate key. Provider-specific identifiers (e.g. Angel One
    symbol tokens) live in a separate mapping so the rest of the system never sees them.
    """

    exchange: str
    symbol: str
    name: str
    instrument_type: str = "EQ"
    lot_size: int = 1
    tick_size: float = 0.05
    expiry: Optional[date] = None
    strike: Optional[float] = None
    instrument_id: Optional[int] = None


@dataclass(frozen=True)
class ProviderInstrument:
    """An instrument as listed by a provider, together with that provider's identifier."""

    instrument: Instrument
    provider: str
    provider_token: str


@dataclass(frozen=True)
class DateRange:
    start: datetime
    end: datetime

    def chunks(self, max_span: timedelta) -> list[DateRange]:
        out: list[DateRange] = []
        cursor = self.start
        while cursor <= self.end:
            chunk_end = min(cursor + max_span, self.end)
            out.append(DateRange(cursor, chunk_end))
            cursor = chunk_end + timedelta(seconds=1)
        return out


@dataclass
class IngestionResult:
    instrument_id: int
    interval: Interval
    requested: DateRange
    rows: int
    status: str = "ok"
    error: Optional[str] = None
    run_id: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)

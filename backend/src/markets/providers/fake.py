"""Deterministic synthetic data for running everything offline (MARKETS_PROVIDER=fake)."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from typing import Iterator, Sequence

import numpy as np
import pandas as pd

from markets.core.models import CANDLE_COLUMNS, DateRange, Instrument, Interval, ProviderInstrument

_UNIVERSE = [
    ("NSE", "RELIANCE-EQ", "RELIANCE", "EQ", 2500.0),
    ("NSE", "TCS-EQ", "TCS", "EQ", 3800.0),
    ("NSE", "INFY-EQ", "INFY", "EQ", 1500.0),
    ("NSE", "HDFCBANK-EQ", "HDFCBANK", "EQ", 1600.0),
    ("NSE", "Nifty 50", "NIFTY", "INDEX", 22000.0),
]

# The random walk always starts here, so a given bar has the same value on every call.
_DAILY_ANCHOR = datetime(2010, 1, 1)
_INTRADAY_ANCHOR = datetime(2024, 1, 1)


class FakeProvider:
    name = "fake"

    def list_instruments(self) -> Iterator[ProviderInstrument]:
        for i, (exchange, symbol, name, itype, _) in enumerate(_UNIVERSE, start=1):
            yield ProviderInstrument(Instrument(exchange, symbol, name, itype), self.name, str(i))

    def close(self) -> None:
        pass

    def last_trade_dates(self, exchange: str, tokens: Sequence[str]) -> dict[str, date]:
        """Every instrument last traded on the most recent weekday."""
        day = date.today()
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        return {t: day for t in tokens}

    def fetch_candles(self, provider_token: str, exchange: str, interval: Interval, window: DateRange) -> pd.DataFrame:
        base_price = _UNIVERSE[int(provider_token) - 1][4]
        anchor = _DAILY_ANCHOR if interval == Interval.D1 else _INTRADAY_ANCHOR
        full = _bar_index(interval, anchor, window.end)
        seed = int(hashlib.md5(f"{provider_token}:{interval.value}".encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)

        returns = rng.normal(0.0003, 0.015 if interval == Interval.D1 else 0.002, len(full))
        close = pd.Series(base_price * np.exp(np.cumsum(returns)), index=full)
        open_ = close.shift(fill_value=base_price)
        wiggle = np.abs(rng.normal(0, 0.005, len(full)))
        df = pd.DataFrame({
            "open": open_,
            "high": np.maximum(open_, close) * (1 + wiggle),
            "low": np.minimum(open_, close) * (1 - wiggle),
            "close": close,
            "volume": rng.integers(100_000, 5_000_000, len(full)).astype(float),
        })[list(CANDLE_COLUMNS)]
        df.index.name = "ts"
        start = pd.Timestamp(window.start)
        if interval == Interval.D1:
            start = start.normalize()
        return df[(df.index >= start) & (df.index <= pd.Timestamp(window.end))]


def _bar_index(interval: Interval, start: datetime, end: datetime) -> pd.DatetimeIndex:
    """Weekday bars; intraday bars run 09:15 to 15:30 IST."""
    days = pd.bdate_range(start.date(), end.date())
    if interval == Interval.D1:
        return pd.DatetimeIndex(days)
    offsets = pd.timedelta_range(start="9h15min", end="15h29min", freq=pd.Timedelta(interval.duration))
    return pd.DatetimeIndex([d + o for d in days for o in offsets])

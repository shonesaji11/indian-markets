"""Helpers shared by the services that serve cross-sectional (one row per instrument) data."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Optional, Sequence

import pandas as pd

from markets.storage.duckdb.repositories import DuckMarketRepository, DuckWatchlistRepository

ALL_TRACKED = "all"  # pseudo-universe: every instrument with daily candles


def universe_members(universe: str, as_of: datetime, watchlists: DuckWatchlistRepository,
                     market: DuckMarketRepository) -> list[int]:
    """Instrument ids of a watchlist as it was on `as_of` (no survivorship bias), falling back to
    today's members when it has no history yet. `ALL_TRACKED` = everything with daily data."""
    if universe == ALL_TRACKED:
        return market.tracked_daily_ids()
    return watchlists.member_ids(universe, as_of) or watchlists.member_ids(universe)


def latest_session(snap: pd.DataFrame) -> tuple[pd.DataFrame, Optional[pd.Timestamp]]:
    """Keep only instruments whose last bar is on the universe's latest trading day."""
    if snap.empty:
        return snap, None
    trading_day = snap["ts"].max()
    return snap[snap["ts"] == trading_day], trading_day


def clean(value: Any) -> Any:
    """JSON-safe scalar: NaN -> None, Timestamp -> ISO string."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def records(df: pd.DataFrame, columns: Sequence[str]) -> list[dict[str, Any]]:
    """Rows as JSON-safe dicts, limited to `columns` that exist in `df`, in that order."""
    cols = [c for c in columns if c in df.columns]
    return [{k: clean(v) for k, v in r.items()} for r in df[cols].to_dict("records")]

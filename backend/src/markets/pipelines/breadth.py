from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Sequence

import pandas as pd

from markets.storage.duckdb.repositories import DuckBreadthRepository

log = logging.getLogger(__name__)

HISTORY_START = datetime(1990, 1, 1)


class BreadthService:
    """Sector breadth: share of each sector's stocks above their N-day SMA.

    Stored daily for `universes` x `periods` (table sector_breadth): kept fresh by the nightly
    update, filled for history by `backfill`, and written through on the first read of a day.
    Other MA periods are computed on request and not stored.
    """

    def __init__(self, repo: DuckBreadthRepository, universes: Sequence[str], periods: Sequence[int]):
        self.repo = repo
        self.universes = tuple(universes)
        self.periods = tuple(periods)

    def update(self, days: int = 10) -> int:
        """Recompute the last `days` calendar days (covers late or revised bars)."""
        end = datetime.now()
        return self._store_all(end - timedelta(days=days), end)

    def backfill(self) -> int:
        return self._store_all(HISTORY_START, datetime.now())

    def _store_all(self, start: datetime, end: datetime) -> int:
        rows = 0
        for universe in self.universes:
            n = self.repo.store(universe, self.periods, start, end)
            log.info("sector breadth %s: %d rows from %s", universe, n, start.date())
            rows += n
        return rows

    def sectors(self, universe: str, as_of: Optional[datetime] = None,
                periods: Sequence[int] = (10, 20)) -> dict[str, Any]:
        """Every sector on the latest session up to `as_of`: stocks and count above each SMA,
        sorted by share above the last period (ties: bigger sectors first)."""
        periods = sorted({int(p) for p in periods})
        if not periods or min(periods) < 1:
            raise ValueError("MA periods must be positive integers")
        day = self.repo.latest_session(as_of or datetime.now())
        if day is None:
            return {"as_of": None, "universe": universe, "periods": periods, "sectors": []}

        cacheable = universe in self.universes
        stored = [p for p in periods if cacheable and p in self.periods]
        frame = self.repo.load(universe, day, stored)
        missing = [p for p in stored if p not in set(frame["ma_period"])]
        if missing:  # first read of this day: compute once and keep it
            self.repo.store(universe, missing, day, day)
            frame = self.repo.load(universe, day, stored)
        live = [p for p in periods if p not in stored]
        if live:
            frame = pd.concat([frame, self.repo.compute(universe, live, day, day)], ignore_index=True)

        return {"as_of": day.isoformat(), "universe": universe, "periods": periods,
                "sectors": _sector_rows(frame, periods)}


def _sector_rows(frame: pd.DataFrame, periods: Sequence[int]) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    above = frame.pivot_table(index="industry", columns="ma_period", values="above", aggfunc="sum")
    stocks = frame.groupby("industry")["stocks"].max()
    key = periods[-1]
    order = sorted(stocks.index, key=lambda ind: (-(above.at[ind, key] / stocks[ind]), -stocks[ind], ind))
    return [
        {
            "industry": ind,
            "stocks": int(stocks[ind]),
            "above": {str(p): int(above.at[ind, p]) for p in periods},
        }
        for ind in order
    ]

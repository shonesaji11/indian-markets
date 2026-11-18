from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Sequence

import pandas as pd

from markets.engine.data_quality import trading_sessions
from markets.engine.screener import ago_sessions
from markets.pipelines.highs import AthService
from markets.pipelines.snapshots import records
from markets.storage.duckdb.repositories import DuckBreadthRepository

log = logging.getLogger(__name__)

HISTORY_START = datetime(1990, 1, 1)
ROTATION_WINDOW = 5  # sessions averaged on each side of a rotation comparison
ROTATION_COLUMNS = ("industry", "stocks", "rank_now", "rank_then", "rank_change", "share_now", "share_then")
HIGH_BASES = ("52w", "ath")  # near-high reference: 52-week high, or all-time high since the first stored bar
RANK_BY = ("ma", "near_high")


class BreadthService:
    """Sector breadth: share of each sector's stocks above their N-day SMA.

    Stored daily for `universes` x `periods` (table sector_breadth): kept fresh by the nightly
    update, filled for history by `backfill`, and written through on the first read of a day.
    Other MA periods are computed on request and not stored.

    Also the share of each sector's stocks closing within N% of their 52-week or all-time high
    ("near high"), always computed on request; the all-time high comes from the daily_ath cache,
    which `ath` brings up to date first.
    """

    def __init__(self, repo: DuckBreadthRepository, universes: Sequence[str], periods: Sequence[int],
                 ath: Optional[AthService] = None):
        self.repo = repo
        self.universes = tuple(universes)
        self.periods = tuple(periods)
        self.ath = ath

    def update(self, days: int = 10, since: Optional[datetime] = None) -> int:
        """Recompute stored breadth from the earliest of: `days` calendar days ago (late or revised
        bars), the earliest daily bar (re)ingested since the last update or backfill (e.g. a
        re-downloaded hole), and `since` (e.g. the earliest bar the repair step removed, which no
        ingestion time can show). A changed bar moves the SMAs after it, so everything from there on
        is recomputed."""
        end = datetime.now()
        start = end - timedelta(days=days)
        mark = self.repo.get_state("breadth_watermark")
        for changed in (self.repo.earliest_changed_bar(datetime.fromisoformat(mark) if mark else None), since):
            if changed is not None and changed < start:
                start = changed
        return self._store_all(start, end)

    def backfill(self) -> int:
        return self._store_all(HISTORY_START, datetime.now())

    def _store_all(self, start: datetime, end: datetime) -> int:
        newest = self.repo.max_ingested_at()  # read first: bars arriving meanwhile are caught next time
        rows = self._store_universes(start, end)
        if newest is not None:
            self.repo.set_state("breadth_watermark", pd.Timestamp(newest).isoformat())
        return rows

    def _store_universes(self, start: datetime, end: datetime) -> int:
        rows = 0
        for universe in self.universes:
            n = self.repo.store(universe, self.periods, start, end)
            log.info("sector breadth %s: %d rows from %s", universe, n, start.date())
            rows += n
        return rows

    def sectors(self, universe: str, as_of: Optional[datetime] = None, periods: Sequence[int] = (10, 20),
                near_pct: float = 10.0, near_basis: str = "52w") -> dict[str, Any]:
        """Every sector on the latest session up to `as_of`: stocks and count above each SMA, and
        `near_high` = {stocks with a reference high, how many closed within `near_pct`% of it}; sorted
        by share above the last period (ties: bigger sectors first)."""
        periods = sorted({int(p) for p in periods})
        if not periods or min(periods) < 1:
            raise ValueError("MA periods must be positive integers")
        _check_near(near_pct, near_basis)
        out: dict[str, Any] = {"as_of": None, "universe": universe, "periods": periods,
                               "near_pct": near_pct, "near_basis": near_basis, "sectors": []}
        day = self.repo.latest_session(as_of or datetime.now())
        if day is None:
            return out

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

        rows = _sector_rows(frame, periods)
        near = self._near_high(universe, near_basis, near_pct, day, day).set_index("industry")
        for r in rows:
            n = near.loc[r["industry"]] if r["industry"] in near.index else None
            r["near_high"] = None if n is None else {"stocks": int(n["stocks"]), "near": int(n["above"])}
        out.update(as_of=day.isoformat(), sectors=rows)
        return out

    def _near_high(self, universe: str, basis: str, pct: float, start: datetime, end: datetime) -> pd.DataFrame:
        """Near-high counts per sector and day (repo.near_high), refreshing the all-time-high cache first."""
        if basis == "ath" and self.ath is not None:
            self.ath.refresh()
        return self.repo.near_high(universe, basis, pct / 100, start, end)

    def rotation(self, universe: str, as_of: Optional[datetime] = None, period: int = 50,
                 ago: Optional[dict[str, Any]] = None, min_stocks: int = 5, rank_by: str = "ma",
                 near_pct: float = 10.0, near_basis: str = "52w") -> dict[str, Any]:
        """Sector rotation: each sector's average daily rank by share of stocks above the `period` SMA
        (`rank_by` 'ma') or within `near_pct`% of their high (`rank_by` 'near_high', see `sectors`)
        over the last ROTATION_WINDOW sessions, against the same average ending `ago` (default 1w)
        earlier. See `rotation_rows`."""
        ago = ago or {"n": 1, "unit": "w"}
        lag = ago_sessions(ago)
        if lag < 1:
            raise ValueError("compare with at least one session back (1d to 12m)")
        if period < 1 or min_stocks < 1:
            raise ValueError("MA period and min stocks must be positive integers")
        if rank_by not in RANK_BY:
            raise ValueError(f"rank_by must be one of {RANK_BY}")
        _check_near(near_pct, near_basis)
        out: dict[str, Any] = {"as_of": None, "universe": universe, "period": period, "ago": ago,
                               "rank_by": rank_by, "near_pct": near_pct, "near_basis": near_basis,
                               "window": ROTATION_WINDOW, "min_stocks": min_stocks, "windows": None,
                               "hidden": 0, "sectors": []}
        day = self.repo.latest_session(as_of or datetime.now())
        if day is None:
            return out
        need = lag + ROTATION_WINDOW
        # Calendar days that hold `need` sessions with room to spare (~1.45 calendar days per session).
        start = day - timedelta(days=2 * need + 20)
        frame = (self._history(universe, period, start, day, need) if rank_by == "ma"
                 else self._near_high(universe, near_basis, near_pct, start, day))
        if frame.empty:
            return out
        # Market sessions only: drops stray days where a handful of stocks have a bar.
        sessions = trading_sessions(frame.groupby("ts")["stocks"].sum())
        if len(sessions) < need:
            raise ValueError(f"needs {need} sessions of breadth data; {len(sessions)} available")
        sessions = sessions[-need:]
        rows, hidden = rotation_rows(frame, sessions, lag, ROTATION_WINDOW, min_stocks)
        out.update(
            as_of=sessions[-1].isoformat(), hidden=hidden, sectors=records(rows, ROTATION_COLUMNS),
            windows={"now": [sessions[-ROTATION_WINDOW].isoformat(), sessions[-1].isoformat()],
                     "then": [sessions[0].isoformat(), sessions[-lag - 1].isoformat()]})
        return out

    def _history(self, universe: str, period: int, start: datetime, end: datetime, sessions: int) -> pd.DataFrame:
        """Breadth rows for one period over [start, end]: stored rows when this universe and period are
        stored and hold at least `sessions` days (the last day written through on first read, as in
        `sectors`), otherwise computed live."""
        if universe in self.universes and period in self.periods:
            frame = self.repo.load_range(universe, period, start, end)
            if frame.empty or frame["ts"].max() < end:
                self.repo.store(universe, [period], end, end)
                frame = self.repo.load_range(universe, period, start, end)
            if frame["ts"].nunique() >= sessions:
                return frame
        return self.repo.compute(universe, [period], start, end)


def _check_near(pct: float, basis: str) -> None:
    if basis not in HIGH_BASES:
        raise ValueError(f"high basis must be one of {HIGH_BASES}")
    if not 0 < pct < 100:
        raise ValueError("near-high distance must be between 0 and 100 percent")


def rotation_rows(frame: pd.DataFrame, sessions: pd.DatetimeIndex, lag: int, window: int,
                  min_stocks: int) -> tuple[pd.DataFrame, int]:
    """Rank change per sector from daily breadth rows (`ts, industry, stocks, above`: one MA period,
    or near-high counts where `above` = stocks near their high).

    Each session in `sessions`, sectors with at least `min_stocks` stocks that day are ranked by share
    `above / stocks` (1 = highest; ties share the average rank). `rank_now` / `share_now` average
    the last `window` sessions, `rank_then` / `share_then` the `window` sessions ending `lag` sessions
    earlier, over the days the sector was ranked. `rank_change` = rank_then - rank_now, so positive means
    climbing towards 1. Rows: sectors with `min_stocks` on the last session, sorted by rank_change
    (missing last), then rank_now. Also returns how many smaller sectors were left out.
    """
    now_days = sessions[-window:]
    then_days = sessions[-(lag + window):len(sessions) - lag]
    df = frame[frame["ts"].isin(sessions) & (frame["stocks"] >= min_stocks)].copy()
    df["share"] = df["above"] / df["stocks"]
    df["rank"] = df.groupby("ts")["share"].rank(ascending=False, method="average")
    now = df[df["ts"].isin(now_days)].groupby("industry")[["rank", "share"]].mean()
    then = df[df["ts"].isin(then_days)].groupby("industry")[["rank", "share"]].mean()

    last = frame[frame["ts"] == sessions[-1]].set_index("industry")["stocks"]
    out = last[last >= min_stocks].rename("stocks").to_frame()
    out["rank_now"], out["share_now"] = now["rank"], now["share"]
    out["rank_then"], out["share_then"] = then["rank"], then["share"]
    out["rank_change"] = out["rank_then"] - out["rank_now"]
    out = out.rename_axis("industry").reset_index()
    out = out.sort_values(["rank_change", "rank_now", "industry"], ascending=[False, True, True], na_position="last")
    return out.reset_index(drop=True), int((last < min_stocks).sum())


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

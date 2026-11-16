from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Sequence

import pandas as pd

from markets.engine.scans import SCANS, breadth
from markets.pipelines.snapshots import latest_session, records, universe_members
from markets.storage.duckdb.repositories import DuckMarketRepository, DuckWatchlistRepository

ROW_COLUMNS = ["instrument_id", "exchange", "symbol", "name", "industry", "ts", "close", "change", "pct_change",
               "gap_pct", "volume", "relative_volume", "high_52w", "low_52w", "from_high_52w"]


def _rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    return records(df, ROW_COLUMNS)


class MarketOverviewService:
    """Assembles the landing page: index tiles, breadth, sector moves and every scan."""

    def __init__(self, market: DuckMarketRepository, watchlists: DuckWatchlistRepository,
                 benchmark_order: Sequence[str] = ()):
        self.market = market
        self.watchlists = watchlists
        # "EXCHANGE:SYMBOL" refs in display order for the index tiles.
        self.benchmark_order = {ref.upper(): n for n, ref in enumerate(benchmark_order)}

    def overview(self, universe: str, as_of: Optional[datetime] = None, limit: int = 10) -> dict[str, Any]:
        as_of = as_of or datetime.now()
        members = universe_members(universe, as_of, self.watchlists, self.market)
        snap = self.market.snapshot(as_of, members)
        equities, trading_day = latest_session(snap[snap["instrument_type"] == "EQ"] if not snap.empty else snap)

        benchmarks = sorted(
            self._index_rows("benchmarks", as_of, sparkline=True),
            key=lambda r: self.benchmark_order.get(f"{r['exchange']}:{r['symbol']}".upper(), len(self.benchmark_order)),
        )
        sectors = sorted(self._index_rows("sectors", as_of), key=lambda r: r["pct_change"] or 0, reverse=True)

        return {
            "as_of": trading_day.isoformat() if trading_day is not None else None,
            "universe": {"id": universe, "members": len(members), "priced": int(len(equities))},
            "benchmarks": benchmarks,
            "sectors": sectors,
            "breadth": breadth(equities),
            "scans": [
                {
                    "name": s.name,
                    "version": s.version,
                    "title": s.title,
                    "description": s.description,
                    "metric": s.metric,
                    "rows": _rows(s.run(equities, limit)),
                }
                for s in SCANS.values()
            ],
        }

    def _index_rows(self, watchlist_id: str, as_of: datetime, sparkline: bool = False) -> list[dict[str, Any]]:
        ids = self.watchlists.member_ids(watchlist_id)
        snap = self.market.snapshot(as_of, ids)
        if snap.empty:
            return []
        # Keep the configured order (benchmarks) by sorting on watchlist position = id order is arbitrary,
        # so the caller sorts sectors by move; benchmarks follow WATCHLISTS order via the spec.
        rows = _rows(snap)
        if sparkline:
            closes = self.market.recent_closes(ids, as_of)
            for r in rows:
                r["spark"] = closes.get(r["instrument_id"], [])
        return rows

    def scan_catalog(self) -> list[dict[str, Any]]:
        return [{"name": s.name, "version": s.version, "title": s.title, "description": s.description}
                for s in SCANS.values()]

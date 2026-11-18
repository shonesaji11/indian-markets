from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Sequence

import pandas as pd

from markets.engine.performance import basket_performance
from markets.engine.registry import IndicatorRegistry
from markets.engine.screener import (
    FIELDS,
    TIMEFRAME,
    bars_ago,
    evaluate,
    indicator_frame,
    iter_operands,
    lookback_bars,
    operand_key,
    operand_label,
    uses_crossovers,
    validate,
)
from markets.pipelines.market_overview import ROW_COLUMNS
from markets.pipelines.snapshots import latest_session, records, universe_members
from markets.storage.duckdb.repositories import (
    DuckInstrumentRepository,
    DuckMarketRepository,
    DuckSavedScanRepository,
    DuckWatchlistRepository,
    UNCLASSIFIED,
)


class ScreenerService:
    """Runs custom scans (engine/screener.py filter trees) over a universe, and stores saved ones."""

    def __init__(self, registry: IndicatorRegistry, market: DuckMarketRepository,
                 watchlists: DuckWatchlistRepository, saved: DuckSavedScanRepository,
                 instruments: DuckInstrumentRepository, benchmark: str = "NSE:Nifty 50"):
        self.registry = registry
        self.market = market
        self.watchlists = watchlists
        self.saved = saved
        self.instruments = instruments
        self.benchmark = benchmark  # "EXCHANGE:SYMBOL" that baskets are compared with

    def fields(self) -> list[dict[str, Any]]:
        return [{"name": f.name, "label": f.label, "percent": f.percent} for f in FIELDS.values()]

    def run(self, filter: dict[str, Any], universe: str, as_of: Optional[datetime] = None,
            include_indices: bool = False, industry: Optional[str] = None,
            columns: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
        """`industry` limits the universe to one sector; `columns` are extra operands to compute and
        return (e.g. SMAs for display) without filtering on them."""
        validate(filter, self.registry)
        for op in columns:
            validate({"type": "condition", "left": op, "op": "gt", "right": {"type": "value", "value": 0}},
                     self.registry)
        as_of = as_of or datetime.now()
        members = universe_members(universe, as_of, self.watchlists, self.market)
        snap = self.market.snapshot(as_of, members)
        if not include_indices and not snap.empty:
            snap = snap[snap["instrument_type"] != "INDEX"]
        if industry is not None and not snap.empty:
            tags = snap["industry"].fillna(UNCLASSIFIED)
            snap = snap[tags == industry]
        snap, trading_day = latest_session(snap)
        snap = snap.set_index("instrument_id", drop=False)
        index = snap.index

        operands = {operand_key(op): op for op in [*iter_operands(filter), *columns]}
        values = self._values(operands, snap, trading_day, uses_crossovers(filter))
        matched = snap[evaluate(filter, values, index)].copy() if len(index) else snap
        for key, (now, _) in values.items():
            matched[key] = now.reindex(matched.index)
        matched = matched.sort_values("symbol")

        return {
            "as_of": trading_day.isoformat() if trading_day is not None else None,
            "timeframe": TIMEFRAME,
            "universe": {"id": universe, "members": len(members), "priced": len(snap), "matched": len(matched)},
            "columns": [self._column(key, op) for key, op in operands.items()],
            "rows": records(matched, list(dict.fromkeys([*ROW_COLUMNS, "instrument_type", *operands]))),
        }

    def _values(self, operands: dict[str, dict], snap: pd.DataFrame, trading_day, need_prev: bool):
        """(value, session before) per operand key. An operand `ago` N sessions reads session N back on
        the universe's calendar; an instrument with no bar on that exact session gets NaN (left out)."""
        index = snap.index
        nan = pd.Series(float("nan"), index=index)
        offsets = {key: bars_ago(op) for key, op in operands.items()}
        needed = set(offsets.values()) | ({n + 1 for n in offsets.values()} if need_prev else set())
        sessions = (self.market.recent_sessions(list(index), trading_day, max(needed) + 1)
                    if needed and trading_day is not None and len(index) else [])
        session = lambda n: sessions[n] if n < len(sessions) else None

        snaps = {0: snap}

        def field_at(field: str, n: int) -> pd.Series:
            if n not in snaps:
                day = session(n)
                rows = self.market.snapshot(day, list(index)) if day is not None else pd.DataFrame()
                rows = rows[rows["ts"] == day] if not rows.empty else rows
                snaps[n] = rows.set_index("instrument_id").reindex(index) if not rows.empty else pd.DataFrame(index=index)
            frame = snaps[n]
            return frame[field].astype("float64") if field in frame else nan

        values = {}
        for key, op in operands.items():
            if op["type"] == "field":
                n = offsets[key]
                values[key] = (field_at(op["field"], n), field_at(op["field"], n + 1) if need_prev else nan)

        indicators = {k: op for k, op in operands.items() if op["type"] == "indicator"}
        if indicators and len(index) and trading_day is not None:
            specs = {k: self.registry.get(op["name"]) for k, op in indicators.items()}
            depth = max(lookback_bars(specs[k], op.get("params") or {}) for k, op in indicators.items()) + max(needed) + 1
            bars = self.market.daily_bars(list(index), trading_day, depth)

            def pick(frame: pd.DataFrame, n: int) -> pd.Series:
                day = session(n)
                if day is None or day not in frame.index:
                    return nan
                return frame.loc[day].reindex(index).astype("float64")

            for key, op in indicators.items():
                spec = specs[key]
                frame = indicator_frame(spec, op.get("params") or {}, op.get("output") or spec.name, bars)
                n = offsets[key]
                values[key] = (pick(frame, n), pick(frame, n + 1) if need_prev else nan)
        else:
            values.update({k: (nan, nan) for k in indicators})
        return values

    def performance(self, instrument_ids: Sequence[int], start: datetime,
                    end: Optional[datetime] = None) -> dict[str, Any]:
        """Equal-weight buy-and-hold of `instrument_ids` picked on `start`'s session and bought at the
        next session's open, up to `end` (default: latest stored), with the benchmark over the same sessions."""
        end = end or datetime.now()
        if end < start:
            raise ValueError("the Until date must be on or after the As of date")
        ids = list(dict.fromkeys(instrument_ids))
        bench = self.instruments.find(*self.benchmark.split(":", 1))
        bars = self.market.daily_prices([*ids, *([bench.instrument_id] if bench else [])], start, end)
        perf = basket_performance(bars[bars["instrument_id"].isin(ids)], start)
        path = perf.path
        benchmark = None
        if bench is not None and not path.empty:
            bpath = basket_performance(bars[bars["instrument_id"] == bench.instrument_id], start).path
            if not bpath.empty:
                aligned = bpath.reindex(bpath.index.union(path.index)).ffill().reindex(path.index)
                benchmark = {"label": bench.symbol, "points": _points(aligned)}
        stocks = perf.stocks.reset_index()
        return {
            "start": path.index[0].isoformat() if not path.empty else None,
            "end": path.index[-1].isoformat() if not path.empty else None,
            "sessions": max(len(path) - 1, 0),
            "total": len(ids),
            "counted": perf.counted,
            "stocks": records(stocks, ["instrument_id", "entry", "close", "change"]),
            "basket": _points(path),
            "benchmark": benchmark,
        }

    @staticmethod
    def _column(key: str, op: dict[str, Any]) -> dict[str, Any]:
        field = FIELDS.get(op.get("field", "")) if op["type"] == "field" else None
        return {"key": key, "label": operand_label(op), "percent": bool(field and field.percent)}

    # --- saved scans ---------------------------------------------------------------------

    def saved_scans(self) -> list[dict[str, Any]]:
        return self.saved.all()

    def save(self, name: str, definition: dict[str, Any]) -> str:
        if not name.strip():
            raise ValueError("a saved scan needs a name")
        validate(definition.get("filter") or {}, self.registry)
        return self.saved.save(name.strip(), definition)

    def delete(self, scan_id: str) -> bool:
        return self.saved.delete(scan_id)


def _points(path: pd.Series) -> list[dict[str, Any]]:
    return [{"ts": ts.isoformat(), "value": None if pd.isna(v) else float(v)} for ts, v in path.items()]

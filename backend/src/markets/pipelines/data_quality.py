from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional, Sequence

import pandas as pd

from markets.engine.data_quality import (
    DQ_VERSION,
    MIN_HISTORY_BARS,
    find_bad_bars,
    find_gaps,
    find_jumps,
    find_short_history,
    find_stale,
    trading_sessions,
)
from markets.storage.duckdb.repositories import DuckDataQualityRepository, DuckWatchlistRepository

log = logging.getLogger(__name__)

# Checks over stored bars, re-run only where bars were (re)ingested since the last run.
BAR_CHECKS = ("gap", "bad_bar", "jump")
# Checks over every current watchlist member (or the last download attempt), cheap enough to run in full.
GLOBAL_CHECKS = ("stale", "short_history", "failed_download")
CHECKS = BAR_CHECKS + GLOBAL_CHECKS
_EVERYTHING = pd.Timestamp("1900-01-01")


class DataQualityService:
    """Runs the data-quality checks (engine/data_quality.py) and keeps `dq_issues` current.

    Incremental by default: bar checks look only at instruments with bars ingested since the last
    run (by ingested_at, so re-downloaded history is re-checked too), from the bar before the first
    new one. The first run, a DQ_VERSION change, or `full=True` checks all history. A run limited to
    some checks or instruments (on demand) doesn't move the watermark.
    """

    def __init__(self, repo: DuckDataQualityRepository, watchlists: DuckWatchlistRepository):
        self.repo = repo
        self.watchlists = watchlists

    def run(self, full: bool = False, checks: Optional[Sequence[str]] = None,
            instrument_ids: Optional[Sequence[int]] = None) -> dict[str, Any]:
        checks = list(checks or CHECKS)
        unknown = set(checks) - set(CHECKS)
        if unknown:
            raise ValueError(f"unknown check(s) {sorted(unknown)}; expected {list(CHECKS)}")
        scoped = instrument_ids is not None or set(checks) != set(CHECKS)
        now = datetime.now()
        newest = self.repo.max_ingested_at()
        mark = self.repo.get_state("watermark")
        same_version = self.repo.get_state("version") == str(DQ_VERSION)
        watermark = datetime.fromisoformat(mark) if mark and same_version and not full and instrument_ids is None else None

        sessions = trading_sessions(self.repo.instruments_per_day())
        out: dict[str, Any] = {"mode": "incremental" if watermark else "full", "checks": {}}

        changed = self.repo.changed_since(watermark, instrument_ids)
        out["instruments_rechecked"] = len(changed)
        bar_checks = [c for c in checks if c in BAR_CHECKS]
        if bar_checks and not changed.empty:
            bars = self.repo.bars_from(changed)
            finders = {"gap": lambda: find_gaps(bars, sessions), "bad_bar": lambda: find_bad_bars(bars),
                       "jump": lambda: find_jumps(bars)}
            for check in bar_checks:
                out["checks"][check] = self._apply(check, finders[check](), now, scope=changed)

        tracked = sorted({i for w in self.watchlists.all() for i in self.watchlists.member_ids(w["watchlist_id"])})
        if instrument_ids is not None:
            tracked = sorted(set(tracked) & set(instrument_ids))
        scope = None if instrument_ids is None else pd.DataFrame(
            {"instrument_id": pd.Series(list(instrument_ids), dtype="int64"), "from_ts": _EVERYTHING})
        if {"stale", "short_history"} & set(checks):
            summary = self.repo.bar_summary(tracked)
            if "stale" in checks:
                out["checks"]["stale"] = self._apply("stale", find_stale(summary["last_ts"], sessions), now, scope)
            if "short_history" in checks:
                found = find_short_history(summary["bars"], summary["first_ts"])
                out["checks"]["short_history"] = self._apply(
                    "short_history", found, now, scope, status="accepted",
                    note=f"expected: new listing, under {MIN_HISTORY_BARS} bars")
        if "failed_download" in checks:
            found = self.repo.failed_downloads()
            if instrument_ids is not None:
                found = found[found["instrument_id"].isin(instrument_ids)]
            out["checks"]["failed_download"] = self._apply("failed_download", found, now, scope)

        if not scoped and newest is not None:
            self.repo.set_state("watermark", pd.Timestamp(newest).isoformat())
            self.repo.set_state("version", str(DQ_VERSION))
        out["open"] = sum(c["issues"] for c in self.repo.counts() if c["status"] == "open")
        log.info("data quality (%s): %s", out["mode"],
                 ", ".join(f"{k} {v['found']} found/{v['new']} new/{v['resolved']} resolved" for k, v in out["checks"].items()))
        return out

    def _apply(self, check: str, found: pd.DataFrame, now: datetime, scope: Optional[pd.DataFrame],
               status: str = "open", note: Optional[str] = None) -> dict[str, int]:
        recorded = self.repo.record(check, found, now, status=status, note=note)
        # Expected issues (short history) are stored as accepted, so they resolve from that state too.
        resolved = self.repo.resolve_missing(check, recorded["issue_id"].tolist(), now, scope,
                                             statuses=("open", "accepted") if status == "accepted" else ("open",))
        return {"found": len(recorded), "new": int(recorded["new"].sum()) if len(recorded) else 0, "resolved": resolved}

    def report(self, status: Optional[str] = "open", check: Optional[str] = None,
               instrument_id: Optional[int] = None, limit: int = 1000) -> dict[str, Any]:
        return {"counts": self.repo.counts(),
                "issues": self.repo.issues(status, check, instrument_id, limit)}

    def accept(self, issue_id: str, note: str) -> bool:
        if not note.strip():
            raise ValueError("accepting an issue needs a note saying why it's fine")
        return self.repo.accept(issue_id, note.strip())

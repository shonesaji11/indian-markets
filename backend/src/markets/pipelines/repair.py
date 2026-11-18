from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd

from markets.core.models import Interval
from markets.pipelines.ingest import IngestionService
from markets.storage.duckdb.repositories import (
    DuckAthRepository,
    DuckCalcRepository,
    DuckCandleRepository,
    DuckDataQualityRepository,
    DuckWatchlistRepository,
)

log = logging.getLogger(__name__)

MAX_PER_RUN = 50                 # re-downloads per night (the provider's rate limit is shared with the update)
MAX_ATTEMPTS = 3                 # re-downloads per issue before a gap is accepted as a provider hole
RETRY_AFTER = timedelta(days=7)  # wait between attempts on the same issue
GAP_UNIVERSES = ("nifty500", "niftytotalmarket", "benchmarks")  # gaps worth re-downloading (stocks that trade)
RATE_LIMITED = "exceeding access rate"  # Angel's rate-limit message; such a failure doesn't count as an attempt
HOLE_NOTE = f"provider hole: still missing after {MAX_ATTEMPTS} re-downloads"
REMOVED_NOTE = "removed bad bar: still bad after re-download (kept in candle_revisions)"
VALID_NOTE = "bar is valid on re-check"


class RepairService:
    """Nightly repair of open data-quality issues, run after the daily bars are fetched.

    - Bad prices (missing/zero/negative price, high below low), any stock: re-download that date; if
      the bar is still bad, remove it (archived in candle_revisions), drop its stored indicator values
      and rebuild the all-time-high cache for that stock from there. The day becomes a gap.
    - Gaps, stocks in GAP_UNIVERSES only: re-download the missing dates. Filled bars resolve the issue at
      the next data-quality run; a gap still open after MAX_ATTEMPTS tries is accepted as a provider hole.

    At most MAX_PER_RUN re-downloads a run, each issue at most once per RETRY_AFTER. A rate-limited
    download isn't counted as an attempt. Bars that are re-downloaded carry a new ingestion time, so
    the all-time-high cache, stored breadth and data-quality checks pick them up by themselves; removed
    bars can't be seen that way, so `run` returns the earliest removed bar for the breadth update.
    """

    def __init__(self, dq: DuckDataQualityRepository, candles: DuckCandleRepository, calcs: DuckCalcRepository,
                 ingestion: IngestionService, watchlists: DuckWatchlistRepository,
                 ath: Optional[DuckAthRepository] = None):
        self.dq = dq
        self.candles = candles
        self.calcs = calcs
        self.ingestion = ingestion
        self.watchlists = watchlists
        self.ath = ath

    def run(self, now: Optional[datetime] = None) -> dict[str, Any]:
        now = now or datetime.now()
        out: dict[str, Any] = {"tried": 0, "bars_written": 0, "removed": 0, "resolved": 0, "rate_limited": 0,
                               "accepted": self.dq.accept_exhausted("gap", MAX_ATTEMPTS, HOLE_NOTE),
                               "earliest_removed": None, "errors": []}
        gap_ids = sorted({i for w in GAP_UNIVERSES for i in self.watchlists.member_ids(w)})
        todo = self.dq.repair_candidates(gap_ids, now - RETRY_AFTER, MAX_ATTEMPTS, MAX_PER_RUN)
        removed_from: dict[int, datetime] = {}
        for issue in todo.itertuples(index=False):
            iid = int(issue.instrument_id)
            start = pd.Timestamp(issue.start_ts).to_pydatetime()
            end = pd.Timestamp(issue.end_ts if pd.notna(issue.end_ts) else issue.start_ts).to_pydatetime()
            end = end.replace(hour=23, minute=59, second=59)
            result = self.ingestion.ingest(iid, Interval.D1, start, end)
            if result.status != "ok" and _rate_limited(result.error):
                out["rate_limited"] += 1
                continue
            self.dq.note_repair_attempt([issue.issue_id], now)
            out["tried"] += 1
            if result.status != "ok":
                out["errors"].append(f"{issue.issue_id}: {result.error}")
                continue
            out["bars_written"] += result.rows
            if issue.check_name != "bad_bar":
                continue
            removed = self.candles.remove_bad_bars(iid, Interval.D1, start, end)
            if removed:
                self.calcs.delete_values_at(iid, Interval.D1, removed)
                removed_from[iid] = min(removed_from.get(iid, removed[0]), removed[0])
                out["removed"] += len(removed)
                out["resolved"] += self.dq.resolve([issue.issue_id], now, REMOVED_NOTE)
            elif result.rows == 0:
                # Nothing re-downloaded and nothing bad left: the next data-quality run wouldn't revisit it.
                out["resolved"] += self.dq.resolve([issue.issue_id], now, VALID_NOTE)

        if removed_from:
            if self.ath is not None:
                self.ath.rebuild_from(pd.DataFrame(
                    {"instrument_id": list(removed_from), "from_ts": pd.to_datetime(list(removed_from.values()))}))
            out["earliest_removed"] = min(removed_from.values()).isoformat()
        log.info("repair: %d tried, %d bars re-downloaded, %d bad bars removed, %d resolved, %d accepted as "
                 "provider holes, %d rate-limited", out["tried"], out["bars_written"], out["removed"],
                 out["resolved"], out["accepted"], out["rate_limited"])
        return out


def _rate_limited(error: Optional[str]) -> bool:
    return RATE_LIMITED in (error or "")

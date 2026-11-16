from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

from markets.core.models import Interval
from markets.pipelines.breadth import BreadthService
from markets.pipelines.ingest import IngestionService
from markets.pipelines.watchlists import WatchlistService
from markets.storage.duckdb.repositories import DuckMarketRepository, DuckWatchlistRepository

log = logging.getLogger(__name__)


@dataclass
class DailyUpdateReport:
    started_at: datetime
    finished_at: Optional[datetime] = None
    instruments_synced: Optional[int] = None
    watchlists: list[dict[str, Any]] = field(default_factory=list)
    targets: int = 0
    ok: int = 0
    failed: int = 0
    bars_written: int = 0
    breadth_rows: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DailyUpdateService:
    """The nightly job: refresh reference data, then fetch new daily bars for everything tracked.

    Tracked = current members of every watchlist + anything that already has daily candles.
    New instruments get their full default history; existing ones only the missing days.
    """

    def __init__(self, ingestion: IngestionService, watchlist_sync: WatchlistService,
                 watchlists: DuckWatchlistRepository, market: DuckMarketRepository,
                 breadth: Optional[BreadthService] = None):
        self.ingestion = ingestion
        self.breadth = breadth
        self.watchlist_sync = watchlist_sync
        self.watchlists = watchlists
        self.market = market
        self._lock = threading.Lock()

    def run(self, sync_instruments: bool = True, sync_watchlists: bool = True) -> DailyUpdateReport:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("a daily update is already running")
        try:
            return self._run(sync_instruments, sync_watchlists)
        finally:
            self._lock.release()

    def _run(self, sync_instruments: bool, sync_watchlists: bool) -> DailyUpdateReport:
        report = DailyUpdateReport(started_at=datetime.now())
        if sync_instruments:
            try:
                report.instruments_synced = self.ingestion.sync_instruments()
            except Exception as exc:  # a stale instrument master is not fatal
                report.errors.append(f"instrument sync: {exc}")
                log.exception("instrument sync failed")
        if sync_watchlists:
            for watchlist_id in self.watchlist_sync.specs:
                try:
                    report.watchlists.append(self.watchlist_sync.sync(watchlist_id))
                except Exception as exc:
                    report.errors.append(f"watchlist {watchlist_id}: {exc}")
                    log.exception("watchlist sync failed: %s", watchlist_id)

        targets = set(self.market.tracked_daily_ids())
        for w in self.watchlists.all():
            targets.update(self.watchlists.member_ids(w["watchlist_id"]))
        report.targets = len(targets)

        t0 = time.monotonic()
        for n, instrument_id in enumerate(sorted(targets), start=1):
            result = self.ingestion.ingest(instrument_id, Interval.D1)
            if result.status == "ok":
                report.ok += 1
                report.bars_written += result.rows
            else:
                report.failed += 1
                report.errors.append(f"instrument {instrument_id}: {result.error}")
            if n % 50 == 0:
                log.info("daily update: %d/%d instruments (%.0fs)", n, len(targets), time.monotonic() - t0)

        if self.breadth is not None:
            try:
                report.breadth_rows = self.breadth.update()
            except Exception as exc:
                report.errors.append(f"sector breadth: {exc}")
                log.exception("sector breadth update failed")

        report.finished_at = datetime.now()
        log.info("daily update done: %d ok, %d failed, %d bars", report.ok, report.failed, report.bars_written)
        return report

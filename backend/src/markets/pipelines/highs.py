from __future__ import annotations

import logging
import threading
from datetime import datetime

import pandas as pd

from markets.storage.duckdb.repositories import DuckAthRepository

log = logging.getLogger(__name__)

ATH_VERSION = 1  # bump on any change to how daily_ath is computed: the next refresh rebuilds it all


class AthService:
    """Keeps daily_ath (each instrument's running all-time high per daily bar) in step with candles.

    Incremental: instruments with daily bars ingested since the last refresh (by candles.ingested_at,
    so re-downloaded history counts too) are recomputed from their earliest such bar. The first
    refresh, an ATH_VERSION change or `full=True` recomputes everything. Runs nightly, before every
    read that uses the table, and via `markets highs --rebuild`.
    """

    def __init__(self, repo: DuckAthRepository):
        self.repo = repo
        self._lock = threading.Lock()  # API requests run in threads; one refresh at a time

    def refresh(self, full: bool = False) -> int:
        """Bring daily_ath up to date; returns rows rewritten (0 when already current)."""
        with self._lock:
            newest = self.repo.max_ingested_at()
            if newest is None:
                return 0
            mark = self.repo.get_state("ath_watermark")
            same_version = self.repo.get_state("ath_version") == str(ATH_VERSION)
            watermark = datetime.fromisoformat(mark) if mark and same_version and not full else None
            if watermark is not None and newest <= watermark:
                return 0
            changed = self.repo.changed_since(watermark)
            rows = self.repo.rebuild_from(changed)
            self.repo.set_state("ath_watermark", pd.Timestamp(newest).isoformat())
            self.repo.set_state("ath_version", str(ATH_VERSION))
            log.info("all-time highs (%s): %d instruments, %d rows",
                     "incremental" if watermark else "full", len(changed), rows)
            return rows

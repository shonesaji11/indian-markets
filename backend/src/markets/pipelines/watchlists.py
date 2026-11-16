from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from markets.core.ports import ConstituentSource, InstrumentRepository
from markets.storage.duckdb.repositories import DuckWatchlistRepository
from markets.universes import WatchlistSpec

log = logging.getLogger(__name__)


class WatchlistService:
    def __init__(self, specs: Sequence[WatchlistSpec], watchlists: DuckWatchlistRepository,
                 instruments: InstrumentRepository, constituents: Optional[ConstituentSource]):
        self.specs = {s.watchlist_id: s for s in specs}
        self.watchlists = watchlists
        self.instruments = instruments
        self.constituents = constituents

    def sync_all(self) -> list[dict[str, Any]]:
        return [self.sync(watchlist_id) for watchlist_id in self.specs]

    def sync(self, watchlist_id: str) -> dict[str, Any]:
        spec = self.specs[watchlist_id]
        source = f"nse_index:{spec.index}" if spec.index else "config"
        self.watchlists.upsert(spec.watchlist_id, spec.name, spec.description, source)

        ids, missing, industries = [], [], {}
        if spec.index:
            if self.constituents is None:
                raise RuntimeError("no constituent source configured")
            for c in self.constituents.constituents(spec.index):
                instrument = self.instruments.find("NSE", f"{c.symbol}-{c.series}")
                if instrument is None:
                    missing.append(c.symbol)
                    continue
                ids.append(instrument.instrument_id)
                if c.industry:
                    industries[instrument.instrument_id] = c.industry
            self.watchlists.set_tags("industry", industries, source)
        else:
            for ref in spec.members:
                exchange, _, symbol = ref.partition(":")
                instrument = self.instruments.find(exchange, symbol)
                if instrument is None:
                    missing.append(ref)
                else:
                    ids.append(instrument.instrument_id)

        result = self.watchlists.set_members(spec.watchlist_id, ids)
        if missing:
            log.warning("%s: %d symbols not in the instrument master: %s", watchlist_id, len(missing), missing[:10])
        return {"watchlist_id": watchlist_id, **result, "missing": missing}

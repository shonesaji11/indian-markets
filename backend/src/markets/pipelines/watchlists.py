from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from markets.core.ports import ConstituentSource, InstrumentRepository, MarketDataProvider
from markets.storage.duckdb.repositories import DuckWatchlistRepository
from markets.universes import WatchlistSpec

log = logging.getLogger(__name__)


class WatchlistService:
    def __init__(self, specs: Sequence[WatchlistSpec], watchlists: DuckWatchlistRepository,
                 instruments: InstrumentRepository, constituents: Optional[ConstituentSource],
                 provider: Optional[MarketDataProvider] = None):
        self.specs = {s.watchlist_id: s for s in specs}
        self.provider = provider
        self.watchlists = watchlists
        self.instruments = instruments
        self.constituents = constituents

    def sync_all(self) -> list[dict[str, Any]]:
        return [self.sync(watchlist_id) for watchlist_id in self.specs]

    def sync(self, watchlist_id: str) -> dict[str, Any]:
        spec = self.specs[watchlist_id]
        if spec.index:
            source = f"nse_index:{spec.index}"
        elif spec.traded_series:
            source = f"{self.provider.name}:traded" if self.provider else "traded"
        else:
            source = "config"
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
        elif spec.traded_series:
            ids = self._traded_ids(spec.traded_series)
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

    def _traded_ids(self, series: Sequence[str]) -> list[int]:
        """NSE stocks in `series` whose last trade fell on the latest session seen across all quotes.

        The latest session comes from the quotes themselves, so weekends and holidays need no calendar.
        Run after the close: mid-session, stocks that haven't traded yet today would be left out.
        A failed quote batch raises, leaving the current membership untouched.
        """
        if self.provider is None:
            raise RuntimeError("no market data provider configured")
        candidates = self.instruments.equity_tokens("NSE", series, self.provider.name)
        dates = self.provider.last_trade_dates("NSE", candidates["token"].tolist())
        if not dates:
            raise RuntimeError("no quotes returned; keeping the current membership")
        latest = max(dates.values())
        traded = candidates["token"].map(dates) == latest
        log.info("traded stocks: %d of %d candidates traded on %s", traded.sum(), len(candidates), latest)
        return candidates.loc[traded, "instrument_id"].tolist()

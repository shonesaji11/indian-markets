"""Composition root: the one place that chooses concrete adapters.

Everything else receives its collaborators through constructors, so tests and
alternative setups (another broker, another database) only change this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from markets.config import Settings, get_settings
from markets.core.ports import ConstituentSource, MarketDataProvider
from markets.engine import IndicatorRegistry, default_registry
from markets.pipelines.breadth import BreadthService
from markets.pipelines.compute import CalcService
from markets.pipelines.daily_update import DailyUpdateService
from markets.pipelines.ingest import IngestionService
from markets.pipelines.market_overview import MarketOverviewService
from markets.pipelines.screener import ScreenerService
from markets.pipelines.watchlists import WatchlistService
from markets.providers import build_provider
from markets.sources.nse_indices import NseIndexSource
from markets.storage.duckdb import (
    Database,
    DuckBreadthRepository,
    DuckCalcRepository,
    DuckCandleRepository,
    DuckIngestionLog,
    DuckInstrumentRepository,
    DuckMarketRepository,
    DuckSavedScanRepository,
    DuckViewRepository,
    DuckWatchlistRepository,
    migrate,
)
from markets.universes import BREADTH_PERIODS, BREADTH_UNIVERSES, WATCHLISTS, WatchlistSpec


@dataclass
class Container:
    settings: Settings
    db: Database
    instruments: DuckInstrumentRepository
    candles: DuckCandleRepository
    ingestion_log: DuckIngestionLog
    calcs: DuckCalcRepository
    views: DuckViewRepository
    watchlists: DuckWatchlistRepository
    market: DuckMarketRepository
    registry: IndicatorRegistry
    provider: MarketDataProvider
    ingestion: IngestionService
    calc_service: CalcService
    watchlist_sync: WatchlistService
    daily_update: DailyUpdateService
    overview: MarketOverviewService
    screener: ScreenerService
    breadth: BreadthService

    def close(self) -> None:
        self.provider.close()
        self.db.close()


def build_container(settings: Optional[Settings] = None, provider: Optional[MarketDataProvider] = None,
                    db: Optional[Database] = None, constituents: Optional[ConstituentSource] = None,
                    watchlist_specs: Sequence[WatchlistSpec] = WATCHLISTS) -> Container:
    settings = settings or get_settings()
    db = db or Database(settings.db_path)
    migrate(db)

    instruments = DuckInstrumentRepository(db)
    candles = DuckCandleRepository(db)
    ingestion_log = DuckIngestionLog(db)
    calcs = DuckCalcRepository(db)
    ingestion_log.fail_orphaned()
    calcs.fail_orphaned()
    watchlists = DuckWatchlistRepository(db)
    market = DuckMarketRepository(db)
    registry = default_registry()
    provider = provider or build_provider(settings)

    ingestion = IngestionService(provider, instruments, candles, ingestion_log)
    watchlist_sync = WatchlistService(watchlist_specs, watchlists, instruments, constituents or NseIndexSource())
    breadth = BreadthService(DuckBreadthRepository(db), BREADTH_UNIVERSES, BREADTH_PERIODS)
    benchmarks = next((s.members for s in watchlist_specs if s.watchlist_id == "benchmarks"), ())

    return Container(
        settings=settings,
        db=db,
        instruments=instruments,
        candles=candles,
        ingestion_log=ingestion_log,
        calcs=calcs,
        views=DuckViewRepository(db),
        watchlists=watchlists,
        market=market,
        registry=registry,
        provider=provider,
        ingestion=ingestion,
        calc_service=CalcService(registry, candles, calcs),
        watchlist_sync=watchlist_sync,
        daily_update=DailyUpdateService(ingestion, watchlist_sync, watchlists, market, breadth),
        overview=MarketOverviewService(market, watchlists, benchmarks),
        breadth=breadth,
        screener=ScreenerService(registry, market, watchlists, DuckSavedScanRepository(db)),
    )

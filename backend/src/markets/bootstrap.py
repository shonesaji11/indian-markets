"""Composition root: the one place that chooses concrete adapters.

Everything else receives its collaborators through constructors, so tests and
alternative setups (another broker, another database) only change this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from markets.config import Settings, get_settings
from markets.core.ports import ConstituentSource, LiveFeed, MarketDataProvider, Notifier
from markets.engine import IndicatorRegistry, default_registry
from markets.notifiers import build_notifier
from markets.pipelines.alerts import AlertService
from markets.pipelines.breadth import BreadthService
from markets.pipelines.compute import CalcService
from markets.pipelines.daily_update import DailyUpdateService
from markets.pipelines.data_quality import DataQualityService
from markets.pipelines.highs import AthService
from markets.pipelines.ingest import IngestionService
from markets.pipelines.live import LiveService
from markets.pipelines.market_overview import MarketOverviewService
from markets.pipelines.movers import MoverService
from markets.pipelines.repair import RepairService
from markets.pipelines.screener import ScreenerService
from markets.pipelines.watchlists import WatchlistService
from markets.providers import build_live_feed, build_provider
from markets.sources.nse_indices import NseIndexSource
from markets.storage.duckdb import (
    Database,
    DuckAlertRepository,
    DuckAthRepository,
    DuckBreadthRepository,
    DuckCalcRepository,
    DuckCandleRepository,
    DuckDataQualityRepository,
    DuckIngestionLog,
    DuckInstrumentRepository,
    DuckMarketRepository,
    DuckMoverRepository,
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
    ath: AthService
    data_quality: DataQualityService
    repair: RepairService
    live: LiveService  # streams only once started (the API server does; CLI commands don't)
    alerts: AlertService  # fires only once started, like `live`
    movers: MoverService

    def close(self) -> None:
        self.alerts.stop()
        self.live.stop()
        self.provider.close()
        self.db.close()


def build_container(settings: Optional[Settings] = None, provider: Optional[MarketDataProvider] = None,
                    db: Optional[Database] = None, constituents: Optional[ConstituentSource] = None,
                    watchlist_specs: Sequence[WatchlistSpec] = WATCHLISTS,
                    live_feed: Optional[LiveFeed] = None, notifier: Optional[Notifier] = None) -> Container:
    """`notifier`: defaults to Telegram when backend/.env sets it up (see notifiers/)."""
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
    watchlist_sync = WatchlistService(watchlist_specs, watchlists, instruments, constituents or NseIndexSource(), provider)
    ath_repo = DuckAthRepository(db)
    ath = AthService(ath_repo)
    breadth = BreadthService(DuckBreadthRepository(db), BREADTH_UNIVERSES, BREADTH_PERIODS, ath)
    dq_repo = DuckDataQualityRepository(db)
    data_quality = DataQualityService(dq_repo, watchlists)
    repair = RepairService(dq_repo, candles, calcs, ingestion, watchlists, ath_repo)
    benchmarks = next((s.members for s in watchlist_specs if s.watchlist_id == "benchmarks"), ())

    def always_streamed() -> list[int]:
        """The Overview's index tiles, your own lists and stocks with an active alert."""
        return [*watchlists.member_ids("benchmarks"), *(i for wl in watchlists.manual_lists() for i in wl["member_ids"]),
                *alerts.instrument_ids()]

    notifier = notifier or build_notifier(settings)
    movers = MoverService(DuckMoverRepository(db), market, watchlists, instruments, notifier, settings.movers_cutoff)
    live = LiveService(live_feed or build_live_feed(provider), instruments, provider.name, always_streamed)
    alerts = AlertService(DuckAlertRepository(db), instruments, live, notifier)

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
        daily_update=DailyUpdateService(ingestion, watchlist_sync, watchlists, market, breadth,
                                        data_quality=data_quality, ath=ath, repair=repair, movers=movers),
        overview=MarketOverviewService(market, watchlists, benchmarks),
        breadth=breadth,
        ath=ath,
        data_quality=data_quality,
        repair=repair,
        live=live,
        alerts=alerts,
        movers=movers,
        screener=ScreenerService(registry, market, watchlists, DuckSavedScanRepository(db), instruments,
                                 *benchmarks[:1]),
    )

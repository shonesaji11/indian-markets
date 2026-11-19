from dataclasses import dataclass

import pytest

from markets.bootstrap import build_container
from markets.config import Settings
from markets.providers.fake import FakeProvider
from markets.storage.duckdb import Database
from markets.universes import WatchlistSpec


@dataclass(frozen=True)
class FakeConstituent:
    symbol: str
    series: str = "EQ"
    company: str = ""
    industry: str = "Testing"


class FakeConstituentSource:
    def __init__(self, symbols=("RELIANCE", "TCS", "INFY", "HDFCBANK")):
        self.symbols = list(symbols)

    def constituents(self, index):
        return [FakeConstituent(s, industry="IT" if s in ("TCS", "INFY") else "Other") for s in self.symbols]


TEST_WATCHLISTS = (
    WatchlistSpec("nifty500", "Test universe", index="test"),
    WatchlistSpec("benchmarks", "Benchmarks", members=("NSE:Nifty 50",)),
    WatchlistSpec("sectors", "Sectors", members=("NSE:Nifty 50",)),
)


@pytest.fixture
def constituents():
    return FakeConstituentSource()


@pytest.fixture
def container(constituents):
    # Telegram off explicitly: backend/.env may hold a real bot token, and tests must never send.
    settings = Settings(provider="fake", telegram_bot_token=None, telegram_chat_id=None)
    c = build_container(settings=settings, provider=FakeProvider(), db=Database(":memory:"),
                        constituents=constituents, watchlist_specs=TEST_WATCHLISTS)
    c.ingestion.sync_instruments()
    yield c
    c.close()


@pytest.fixture
def reliance_id(container):
    return container.instruments.find("NSE", "RELIANCE-EQ").instrument_id

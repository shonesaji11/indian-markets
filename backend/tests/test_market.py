from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import Interval
from markets.engine.scans import SCANS, breadth
from markets.providers.ratelimit import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_rate_limiter_respects_every_window():
    clock = FakeClock()
    limiter = RateLimiter([(2, 1.0), (5, 60.0)], clock=clock, sleep=clock.sleep)
    times = []
    for _ in range(7):
        limiter.acquire()
        times.append(clock.now)
    assert times[1] < 1.0 <= times[2]  # 2 per second
    assert times[5] >= 60.0  # the 6th call waits for the per-minute window
    for i in range(len(times)):
        in_minute = [t for t in times if times[i] - 60.0 < t <= times[i]]
        assert len(in_minute) <= 5


def snapshot(rows):
    base = {"instrument_type": "EQ", "high": 100.0, "low": 90.0, "close": 95.0, "high_52w": 120.0,
            "low_52w": 80.0, "bars_252": 252, "gap_pct": 0.0, "relative_volume": 1.0, "sma_50": 90.0,
            "sma_200": 100.0}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_scans_rank_and_filter():
    df = snapshot([
        {"symbol": "A", "pct_change": 0.05, "relative_volume": 3.0},
        {"symbol": "B", "pct_change": -0.04, "gap_pct": -0.03},
        {"symbol": "C", "pct_change": 0.01, "high": 121.0, "high_52w": 121.0},
        {"symbol": "D", "pct_change": 0.0},
        {"symbol": "E", "pct_change": 0.02, "high": 130.0, "high_52w": 130.0, "bars_252": 30},  # new listing
    ])
    assert SCANS["top_gainers"].run(df)["symbol"].tolist() == ["A", "E", "C"]
    assert SCANS["top_losers"].run(df)["symbol"].tolist() == ["B"]
    assert SCANS["volume_shockers"].run(df)["symbol"].tolist() == ["A"]
    assert SCANS["new_52w_highs"].run(df)["symbol"].tolist() == ["C"]
    assert SCANS["gap_downs"].run(df)["symbol"].tolist() == ["B"]

    b = breadth(df)
    assert (b["advances"], b["declines"], b["unchanged"]) == (3, 1, 1)
    assert b["above_sma_50"] == 1.0 and b["above_sma_200"] == 0.0
    assert b["new_highs"] == 1


def test_watchlist_membership_keeps_history(container, constituents):
    first = container.watchlist_sync.sync("nifty500")
    assert first["members"] == 4 and first["added"] == 4
    # DuckDB's clock, not Python's: on Windows the two can disagree by a few ms.
    before_change = container.db.cursor().execute("SELECT now()::TIMESTAMP").fetchone()[0]

    constituents.symbols = ["RELIANCE", "TCS", "INFY"]  # HDFCBANK leaves the index
    second = container.watchlist_sync.sync("nifty500")
    assert (second["added"], second["removed"]) == (0, 1)

    hdfc = container.instruments.find("NSE", "HDFCBANK-EQ").instrument_id
    assert hdfc not in container.watchlists.member_ids("nifty500")
    assert hdfc in container.watchlists.member_ids("nifty500", as_of=before_change)


def test_daily_update_fetches_watchlists_and_tracked(container):
    report = container.daily_update.run(sync_instruments=False)
    assert report.failed == 0
    assert report.targets == 5  # 4 constituents + Nifty 50 (benchmarks and sectors overlap)
    assert report.bars_written > 0

    again = container.daily_update.run(sync_instruments=False)
    assert again.ok == 5 and again.bars_written <= 5  # incremental: only the latest bar is re-checked


def test_daily_update_retries_failures_once(container, monkeypatch):
    provider = container.ingestion.provider
    real_fetch = provider.fetch_candles
    tokens = {container.instruments.provider_token(container.instruments.find("NSE", s).instrument_id, provider.name)
              for s in ("TCS-EQ", "INFY-EQ")}
    transient, persistent = sorted(tokens)
    calls = []

    def flaky_fetch(token, *args):
        calls.append(token)
        if token == persistent or (token == transient and calls.count(token) == 1):
            raise RuntimeError("Access denied because of exceeding access rate")
        return real_fetch(token, *args)

    monkeypatch.setattr(provider, "fetch_candles", flaky_fetch)
    container.daily_update.retry_delay = 0
    report = container.daily_update.run(sync_instruments=False)

    assert report.targets == 5 and report.retried == 2
    assert report.ok == 4 and report.failed == 1  # the transient one recovered on the retry pass
    assert calls.count(transient) == 2 and calls.count(persistent) == 2  # retried once, not more
    assert len(report.errors) == 1 and "exceeding access rate" in report.errors[0]


def test_daily_update_skips_retry_pass_when_all_ok(container, monkeypatch):
    slept = []
    monkeypatch.setattr("markets.pipelines.daily_update.time.sleep", slept.append)
    report = container.daily_update.run(sync_instruments=False)
    assert report.retried == 0 and report.failed == 0 and slept == []


def test_traded_watchlist_keeps_stocks_from_latest_session(container, monkeypatch):
    from datetime import date

    from markets.pipelines.watchlists import WatchlistService
    from markets.universes import WatchlistSpec

    spec = WatchlistSpec("traded", "Traded", traded_series=("EQ",))
    service = WatchlistService([spec], container.watchlists, container.instruments, None, container.provider)
    find = lambda s: container.instruments.find("NSE", s).instrument_id  # noqa: E731
    token = lambda s: container.instruments.provider_token(find(s), container.provider.name)  # noqa: E731

    candidates = container.instruments.equity_tokens("NSE", ("EQ",), container.provider.name)
    assert len(candidates) == 4  # the index is not an equity

    # HDFCBANK last traded a day earlier (suspended); INFY has no quote at all.
    quotes = {token("RELIANCE-EQ"): date(2026, 11, 17), token("TCS-EQ"): date(2026, 11, 17),
              token("HDFCBANK-EQ"): date(2026, 11, 14)}
    monkeypatch.setattr(container.provider, "last_trade_dates", lambda exchange, tokens: quotes)
    result = service.sync("traded")
    assert result["members"] == 2
    assert sorted(container.watchlists.member_ids("traded")) == sorted([find("RELIANCE-EQ"), find("TCS-EQ")])

    # No quotes at all (Angel down): fail loudly and keep yesterday's members.
    monkeypatch.setattr(container.provider, "last_trade_dates", lambda exchange, tokens: {})
    with pytest.raises(RuntimeError, match="keeping the current membership"):
        service.sync("traded")
    assert len(container.watchlists.member_ids("traded")) == 2


def test_overview_endpoint(container, reliance_id):
    container.watchlist_sync.sync_all()
    for ref in ("RELIANCE-EQ", "TCS-EQ", "INFY-EQ", "HDFCBANK-EQ", "Nifty 50"):
        iid = container.instruments.find("NSE", ref).instrument_id
        container.ingestion.ingest(iid, Interval.D1, datetime(2023, 1, 1), datetime(2024, 12, 31))

    with TestClient(create_app(container)) as client:
        data = client.get("/api/market/overview", params={"as_of": "2024-06-28", "universe": "nifty500"}).json()

    assert data["as_of"].startswith("2024-06-28")
    assert data["universe"]["priced"] == 4
    assert data["benchmarks"][0]["symbol"] == "Nifty 50" and len(data["benchmarks"][0]["spark"]) == 60
    assert data["breadth"]["advances"] + data["breadth"]["declines"] + data["breadth"]["unchanged"] == 4
    gainers = next(s for s in data["scans"] if s["name"] == "top_gainers")["rows"]
    assert all(r["pct_change"] > 0 for r in gainers)
    assert all(r["ts"].startswith("2024-06-28") for r in gainers)
    assert {r["industry"] for r in gainers} <= {"IT", "Other"}


def test_daily_signals_macro_matches_pandas(container, reliance_id):
    container.ingestion.ingest(reliance_id, Interval.D1, datetime(2023, 1, 1), datetime(2024, 12, 31))
    as_of = datetime(2024, 6, 28, 23, 59)
    row = container.market.snapshot(as_of, [reliance_id]).iloc[0]
    c = container.candles.load(reliance_id, Interval.D1, end=as_of)
    assert row["sma_50"] == pytest.approx(c["close"].tail(50).mean())
    assert row["avg_volume_20d"] == pytest.approx(c["volume"].iloc[-21:-1].mean())
    assert row["gap_pct"] == pytest.approx(c["open"].iloc[-1] / c["close"].iloc[-2] - 1)

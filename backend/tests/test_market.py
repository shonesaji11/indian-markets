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
    persistent_symbol = next(s for s in ("TCS-EQ", "INFY-EQ") if container.instruments.provider_token(
        container.instruments.find("NSE", s).instrument_id, provider.name) == persistent)
    assert report.failed_symbols == [persistent_symbol]


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


def test_daily_update_counts_new_instruments(container):
    first = container.daily_update.run(sync_instruments=False)
    assert first.new_instruments == 5 and first.new_bars == first.bars_written > 0  # nothing stored yet

    again = container.daily_update.run(sync_instruments=False)
    assert again.new_instruments == 0 and again.new_bars == 0


def _report(**overrides):
    r = {"started_at": "2026-11-18T18:00:01.500000", "finished_at": "2026-11-18T19:31:35", "targets": 3038, "ok": 3038,
         "failed": 0, "retried": 2, "bars_written": 13556, "new_instruments": 9, "new_bars": 10558,
         "failed_symbols": [], "breadth_rows": 2240, "errors": [],
         "watchlists": [{"watchlist_id": "nse_traded", "members": 3003, "added": 9, "removed": 13},
                        {"watchlist_id": "nifty50", "members": 50, "added": 0, "removed": 0}],
         "data_quality": {"mode": "full", "instruments_rechecked": 3038, "open": 18249, "checks": {
             "gap": {"found": 15712, "new": 15712, "resolved": 0},
             "bad_bar": {"found": 2213, "new": 2213, "resolved": 0},
             "jump": {"found": 302, "new": 302, "resolved": 1},
             "stale": {"found": 0, "new": 0, "resolved": 0},
             "short_history": {"found": 457, "new": 457, "resolved": 0}}}}
    return {**r, **overrides}


def test_summary_block_normal_night():
    from markets.cli import summary_block

    assert summary_block(_report(), scheduled=True) == (
        "2026-11-18  18:00-19:31 (1h31m)  scheduled\n"
        "  stocks:   3,038/3,038 ok, 0 failed (2 retried)\n"
        "  bars:     13,556 (existing stocks 2,998; 9 new stocks backfilled 10,558)\n"
        "  breadth:  2,240 rows\n"
        "  lists:    nse_traded +9 -13; others unchanged\n"
        "  quality:  18,249 open; +18,684 new, -1 resolved (full): gap +15,712, bad_bar +2,213, jump +302 -1\n"
        "  failed:   -\n\n")


def test_summary_block_failures_holiday_and_missing_dq():
    from datetime import datetime

    from markets.cli import summary_block

    failed = [f"S{i}-EQ" for i in range(7)]
    text = summary_block(_report(
        started_at=datetime(2026, 11, 20, 17, 0), finished_at=datetime(2026, 11, 20, 17, 12),  # direct-run datetimes
        ok=3031, failed=7, bars_written=0, new_instruments=0, new_bars=0, failed_symbols=failed,
        errors=[f"instrument {i}: rate" for i in range(7)] + ["sector breadth: boom"],
        watchlists=[{"watchlist_id": "nifty50", "members": 50, "added": 0, "removed": 0}], data_quality=None,
    ), scheduled=False)
    assert text.endswith("\n\n") and text.rstrip("\n").splitlines() == [
        "2026-11-20  17:00-17:12 (12m)  manual",
        "  stocks:   3,031/3,038 ok, 7 failed (2 retried)",
        "  bars:     0 (no new bars: market holiday?)",
        "  breadth:  2,240 rows",
        "  lists:    no changes",
        "  quality:  not run",
        "  failed:   S0-EQ, S1-EQ, S2-EQ, S3-EQ, S4-EQ +2 more",
        "  errors:   1 other (see update-2026-11-20.log)",
    ]


def test_summary_block_existing_stocks_only():
    from markets.cli import summary_block

    text = summary_block(_report(bars_written=3001, new_instruments=0, new_bars=0, watchlists=[]), scheduled=True)
    assert "  bars:     3,001\n" in text and "  lists:    no changes\n" in text


def test_append_summary_adds_blocks(tmp_path, monkeypatch):
    import markets.config
    from markets.cli import _append_summary

    monkeypatch.setattr(markets.config, "BACKEND_DIR", tmp_path)
    _append_summary(_report(), scheduled=True)
    _append_summary(_report(), scheduled=False)
    text = (tmp_path / "logs" / "nightly-summary.log").read_text(encoding="utf-8")
    assert text.count("2026-11-18  18:00-19:31") == 2  # appended, not overwritten
    assert text.index("scheduled\n") < text.index("manual\n")


def test_summary_block_from_older_server_without_new_fields():
    from markets.cli import summary_block

    old = {k: v for k, v in _report(failed=2, ok=3036).items()
           if k not in ("new_instruments", "new_bars", "failed_symbols")}
    old["errors"] = ["instrument 1: rate", "instrument 2: rate"]
    text = summary_block(old, scheduled=True)
    assert "  bars:     13,556\n" in text
    assert "  failed:   2 (see update-2026-11-18.log)\n" in text and "errors:" not in text

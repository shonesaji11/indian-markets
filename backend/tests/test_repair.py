"""Nightly data repair (pipelines/repair.py): re-download fixable issues, remove bars still bad,
keep derived data in step."""

from datetime import datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import Instrument, Interval, ProviderInstrument
from markets.pipelines import repair as repair_mod

STOCKS = ("RELIANCE-EQ", "TCS-EQ", "INFY-EQ", "HDFCBANK-EQ")
BAD_DAY = datetime(2024, 3, 6)
HOLE = (datetime(2024, 4, 8), datetime(2024, 4, 10))  # three weekday sessions


@pytest.fixture
def loaded(container):
    container.watchlist_sync.sync_all()
    for ref in (*STOCKS, "Nifty 50"):
        container.ingestion.ingest(iid(container, ref), Interval.D1, datetime(2023, 1, 1), datetime(2024, 6, 28))
    container.data_quality.run(full=True)
    container.ath.refresh()
    container.breadth.backfill()
    return container


def iid(c, sym):
    return c.instruments.find("NSE", sym).instrument_id


def bar(c, sym, ts):
    df = c.candles.load(iid(c, sym), Interval.D1, start=ts, end=ts)
    return None if df.empty else df.iloc[0]


def set_bar(c, sym, ts, **values):
    df = c.candles.load(iid(c, sym), Interval.D1, start=ts, end=ts)
    for k, v in values.items():
        df[k] = v
    c.candles.upsert(iid(c, sym), Interval.D1, df, "test")


def issue(c, check, sym, ts):
    rows = c.db.cursor().execute(
        "SELECT issue_id, status, note, repair_attempts FROM dq_issues WHERE check_name = ? AND instrument_id = ?"
        " AND start_ts = ?", [check, iid(c, sym), ts]).fetchall()
    return rows[0] if rows else None


def make_bad_bar(c, sym="TCS-EQ", ts=BAD_DAY):
    set_bar(c, sym, ts, close=0.0)
    c.data_quality.run()
    assert issue(c, "bad_bar", sym, ts)[1] == "open"


def keep_bad_on_download(c, monkeypatch, sym="TCS-EQ", ts=BAD_DAY):
    """The provider keeps returning that bar with a zero close."""
    real = c.provider.fetch_candles
    token = c.instruments.provider_token(iid(c, sym), c.provider.name)

    def fetch(provider_token, exchange, interval, window):
        df = real(provider_token, exchange, interval, window)
        if provider_token == token and ts in df.index:
            df.loc[ts, "close"] = 0.0
        return df
    monkeypatch.setattr(c.provider, "fetch_candles", fetch)


def make_hole(c, sym="INFY-EQ"):
    c.db.cursor().execute("DELETE FROM candles WHERE instrument_id = ? AND timeframe = '1d' AND ts BETWEEN ? AND ?",
                          [iid(c, sym), *HOLE])
    c.data_quality.run(full=True)  # a deletion has no new ingestion time: only a full check sees it
    assert issue(c, "gap", sym, HOLE[0])[1] == "open"


def drop_on_download(c, monkeypatch, sym="INFY-EQ"):
    """The provider has a hole: those dates never come back."""
    real = c.provider.fetch_candles
    token = c.instruments.provider_token(iid(c, sym), c.provider.name)

    def fetch(provider_token, exchange, interval, window):
        df = real(provider_token, exchange, interval, window)
        return df[~((df.index >= HOLE[0]) & (df.index <= HOLE[1]))] if provider_token == token else df
    monkeypatch.setattr(c.provider, "fetch_candles", fetch)


# --- bad prices -------------------------------------------------------------------------------

def test_bad_bar_fixed_by_redownload(loaded):
    make_bad_bar(loaded)
    report = loaded.daily_update.repair_now()
    assert report["repair"]["tried"] == 1 and report["repair"]["removed"] == 0
    assert bar(loaded, "TCS-EQ", BAD_DAY)["close"] > 0  # the provider's good bar is back
    assert issue(loaded, "bad_bar", "TCS-EQ", BAD_DAY)[1] == "resolved"  # by the data-quality re-check
    assert not report["errors"]


def test_bad_bar_still_bad_is_removed_and_derived_data_follows(loaded, monkeypatch):
    make_bad_bar(loaded)
    keep_bad_on_download(loaded, monkeypatch)
    tcs = iid(loaded, "TCS-EQ")
    loaded.calc_service.compute("sma", tcs, Interval.D1, {"period": 5})
    report = loaded.daily_update.repair_now()

    assert report["repair"]["removed"] == 1 and report["repair"]["earliest_removed"].startswith("2024-03-06")
    assert bar(loaded, "TCS-EQ", BAD_DAY) is None
    archived = loaded.db.cursor().execute(
        "SELECT close FROM candle_revisions WHERE instrument_id = ? AND ts = ?", [tcs, BAD_DAY]).fetchall()
    assert (0.0,) in archived
    status, note = issue(loaded, "bad_bar", "TCS-EQ", BAD_DAY)[1:3]
    assert status == "resolved" and note == repair_mod.REMOVED_NOTE
    # Derived data: no indicator value or all-time high left at the removed bar, breadth recomputed without it.
    cur = loaded.db.cursor()
    assert cur.execute("SELECT count(*) FROM calc_values WHERE instrument_id = ? AND ts = ?", [tcs, BAD_DAY]).fetchone()[0] == 0
    assert cur.execute("SELECT count(*) FROM daily_ath WHERE instrument_id = ? AND ts = ?", [tcs, BAD_DAY]).fetchone()[0] == 0
    stored = cur.execute("SELECT stocks FROM sector_breadth WHERE universe = 'nifty500' AND industry = 'IT'"
                         " AND ma_period = 20 AND ts = ?", [BAD_DAY]).fetchone()[0]
    assert stored == 1  # INFY only: TCS has no bar that day any more


def test_rate_limited_download_is_not_an_attempt(loaded, monkeypatch):
    make_bad_bar(loaded)

    def limited(*args, **kwargs):
        raise RuntimeError("Couldn't parse the JSON response: b'Access denied because of exceeding access rate'")
    monkeypatch.setattr(loaded.provider, "fetch_candles", limited)
    r = loaded.repair.run()
    assert r["rate_limited"] == 1 and r["tried"] == 0
    assert issue(loaded, "bad_bar", "TCS-EQ", BAD_DAY)[3] == 0


# --- gaps ---------------------------------------------------------------------------------------

def test_gap_filled_by_redownload(loaded):
    make_hole(loaded)
    report = loaded.daily_update.repair_now()
    assert report["repair"]["tried"] == 1 and report["repair"]["bars_written"] == 3
    assert bar(loaded, "INFY-EQ", HOLE[0]) is not None
    assert issue(loaded, "gap", "INFY-EQ", HOLE[0])[1] == "resolved"


def test_provider_hole_retried_weekly_then_accepted(loaded, monkeypatch):
    make_hole(loaded)
    drop_on_download(loaded, monkeypatch)
    now = datetime(2026, 11, 20)
    for week in range(repair_mod.MAX_ATTEMPTS):
        r = loaded.repair.run(now + timedelta(weeks=week))
        assert r["tried"] == 1 and r["bars_written"] == 0
        if week < repair_mod.MAX_ATTEMPTS - 1:
            assert loaded.repair.run(now + timedelta(weeks=week, days=1))["tried"] == 0  # not again within a week
    assert issue(loaded, "gap", "INFY-EQ", HOLE[0])[1:4] == ("open", None, repair_mod.MAX_ATTEMPTS)
    # The next run (in the nightly job: after the data-quality run had its chance to resolve it) accepts it.
    r = loaded.repair.run(now + timedelta(weeks=repair_mod.MAX_ATTEMPTS - 1, days=1))
    assert r["accepted"] == 1 and r["tried"] == 0
    assert issue(loaded, "gap", "INFY-EQ", HOLE[0])[1:3] == ("accepted", repair_mod.HOLE_NOTE)


def test_gaps_outside_the_repair_universes_are_left_alone(loaded, monkeypatch):
    make_hole(loaded)
    monkeypatch.setattr(repair_mod, "GAP_UNIVERSES", ("sectors",))  # INFY isn't in it
    assert loaded.repair.run()["tried"] == 0


def test_per_run_limit(loaded, monkeypatch):
    make_bad_bar(loaded)
    make_hole(loaded)
    monkeypatch.setattr(repair_mod, "MAX_PER_RUN", 1)
    r = loaded.repair.run()
    assert r["tried"] == 1
    assert issue(loaded, "bad_bar", "TCS-EQ", BAD_DAY)[3] == 1  # bad prices go first
    assert issue(loaded, "gap", "INFY-EQ", HOLE[0])[3] == 0


# --- breadth catches up with old changes, nightly wiring, NSE test symbols --------------------------

def test_breadth_update_recomputes_from_a_redownloaded_old_bar(loaded):
    loaded.breadth.update()  # sets the watermark
    old = datetime(2023, 6, 1)
    loaded.db.cursor().execute("DELETE FROM sector_breadth WHERE ts = ?", [old])  # stale/missing stored rows
    set_bar(loaded, "INFY-EQ", old, close=bar(loaded, "INFY-EQ", old)["close"] * 1.5)  # a revised old bar
    loaded.breadth.update()  # far older than the 10-day window, yet recomputed
    assert loaded.db.cursor().execute("SELECT count(*) FROM sector_breadth WHERE ts = ?", [old]).fetchone()[0] > 0


def test_nightly_update_runs_repair_before_derived_steps(loaded, monkeypatch):
    make_bad_bar(loaded)
    keep_bad_on_download(loaded, monkeypatch)
    report = loaded.daily_update.run(sync_instruments=False, sync_watchlists=False)
    assert report.repair["removed"] == 1 and not [e for e in report.errors if "repair" in e]


def test_nse_test_symbols_are_not_equities(container):
    container.instruments.upsert_many([ProviderInstrument(Instrument("NSE", "011NSETEST-EQ", "011NSETEST", "EQ"),
                                                          container.provider.name, "99")])
    container.instruments.upsert_many(list(container.provider.list_instruments()))
    symbols = {container.instruments.get(i).symbol
               for i in container.instruments.equity_tokens("NSE", ("EQ",), container.provider.name)["instrument_id"]}
    assert "011NSETEST-EQ" not in symbols and "TCS-EQ" in symbols


def test_repair_api(loaded):
    make_bad_bar(loaded)
    with TestClient(create_app(loaded)) as client:
        body = client.post("/api/jobs/repair").json()
        assert body["repair"]["tried"] == 1 and body["data_quality"] is not None

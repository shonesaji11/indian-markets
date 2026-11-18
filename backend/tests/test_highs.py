"""All-time-high cache (daily_ath) and sector near-high breadth (52-week / all-time)."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import Interval
from markets.pipelines import highs
from markets.pipelines.breadth import ROTATION_WINDOW, rotation_rows

STOCKS = ("RELIANCE-EQ", "TCS-EQ", "INFY-EQ", "HDFCBANK-EQ")
AS_OF = datetime(2024, 6, 28, 23, 59)


@pytest.fixture
def loaded(container):
    container.watchlist_sync.sync_all()  # industries: TCS, INFY = IT; the rest = Other
    for ref in (*STOCKS, "Nifty 50"):
        iid = container.instruments.find("NSE", ref).instrument_id
        container.ingestion.ingest(iid, Interval.D1, datetime(2023, 1, 1), datetime(2024, 12, 31))
    return container


def iid(c, sym):
    return c.instruments.find("NSE", sym).instrument_id


def stored_ath(c):
    return c.db.cursor().execute("SELECT instrument_id, ts, ath FROM daily_ath ORDER BY 1, 2").df()


def expected_ath(c):
    """Running max of valid (finite, positive) highs per instrument, from pandas."""
    bars = c.db.cursor().execute(
        "SELECT instrument_id, ts, high FROM candles WHERE timeframe = '1d' ORDER BY 1, 2").df()
    valid = bars["high"].where(np.isfinite(bars["high"]) & (bars["high"] > 0))
    # cummax leaves NaN on a skipped bar; the running high carries over it
    bars["ath"] = valid.groupby(bars["instrument_id"]).cummax().groupby(bars["instrument_id"]).ffill()
    return bars[["instrument_id", "ts", "ath"]]


def set_bar(c, sym, ts, **values):
    """Overwrite one daily bar (as a re-download would), keeping its other fields."""
    i = iid(c, sym)
    bar = c.candles.load(i, Interval.D1, start=ts, end=ts)
    for k, v in values.items():
        bar[k] = v
    c.candles.upsert(i, Interval.D1, bar, "test")


def assert_ath_matches(c):
    got, exp = stored_ath(c), expected_ath(c)
    pd.testing.assert_frame_equal(got.reset_index(drop=True), exp.reset_index(drop=True), check_dtype=False)


# --- the cache --------------------------------------------------------------------------------

def test_first_refresh_builds_everything_then_nothing_to_do(loaded):
    rows = loaded.ath.refresh()
    assert rows == len(expected_ath(loaded)) > 0
    assert_ath_matches(loaded)
    assert loaded.ath.refresh() == 0  # no new bars since


def test_revised_old_bar_recomputes_only_that_stock_from_that_day(loaded):
    loaded.ath.refresh()
    ts = datetime(2023, 3, 1)
    set_bar(loaded, "TCS-EQ", ts, high=10_000.0)  # a revised old bar becomes the new all-time high
    rows = loaded.ath.refresh()
    tcs = loaded.candles.load(iid(loaded, "TCS-EQ"), Interval.D1)
    assert rows == (tcs.index >= ts).sum()  # one stock, from the changed bar on
    assert_ath_matches(loaded)
    after = stored_ath(loaded).query("instrument_id == @iid(@loaded, 'TCS-EQ') and ts >= @ts")
    assert (after["ath"] == 10_000.0).all()


def test_zero_and_nan_highs_are_skipped(loaded):
    loaded.ath.refresh()
    first = loaded.candles.load(iid(loaded, "INFY-EQ"), Interval.D1).index[0]
    set_bar(loaded, "INFY-EQ", first, high=0.0)
    set_bar(loaded, "INFY-EQ", datetime(2023, 6, 1), high=float("nan"))
    loaded.ath.refresh()
    assert_ath_matches(loaded)
    infy = stored_ath(loaded).query("instrument_id == @iid(@loaded, 'INFY-EQ')")
    assert pd.isna(infy["ath"].iloc[0]) and infy["ath"].iloc[1:].notna().all()


def test_version_change_or_full_rebuilds_everything(loaded, monkeypatch):
    total = loaded.ath.refresh()
    assert loaded.ath.refresh(full=True) == total
    monkeypatch.setattr(highs, "ATH_VERSION", highs.ATH_VERSION + 1)
    assert loaded.ath.refresh() == total
    assert loaded.ath.refresh() == 0


def test_daily_update_refreshes_the_cache(loaded):
    report = loaded.daily_update.run(sync_instruments=False, sync_watchlists=False)
    assert not [e for e in report.errors if "all-time" in e]
    assert report.ath_rows == len(expected_ath(loaded))
    assert_ath_matches(loaded)


# --- near-high breadth ------------------------------------------------------------------------

def expected_near(c, day, basis, pct):
    """Sector -> (stocks with a reference high, stocks within pct of it) from pandas."""
    out = {}
    for sym in STOCKS:
        bars = c.candles.load(iid(c, sym), Interval.D1, end=day)
        valid = bars["high"].where(np.isfinite(bars["high"]) & (bars["high"] > 0))
        ref = (valid.rolling(252, min_periods=1).max() if basis == "52w" else valid.cummax().ffill()).iloc[-1]
        sector = "IT" if sym in ("TCS-EQ", "INFY-EQ") else "Other"
        stocks, near = out.get(sector, (0, 0))
        out[sector] = (stocks + 1, near + int(bars["close"].iloc[-1] >= ref * (1 - pct)))
    return out


def got_near(c, day, basis, pct):
    if basis == "ath":
        c.ath.refresh()
    df = c.breadth.repo.near_high("nifty500", basis, pct, day, day)
    assert (df["ts"] == day).all()
    return {r.industry: (r.stocks, r.above) for r in df.itertuples()}


@pytest.mark.parametrize("basis", ["52w", "ath"])
@pytest.mark.parametrize("as_of", [datetime(2023, 3, 31), datetime(2024, 6, 28)])  # short and long history
def test_near_high_matches_pandas(loaded, basis, as_of):
    day = loaded.breadth.repo.latest_session(as_of)
    for pct in (0.02, 0.10, 0.30):
        assert got_near(loaded, day, basis, pct) == expected_near(loaded, day, basis, pct)


def test_near_high_threshold_both_sides(loaded):
    day = loaded.breadth.repo.latest_session(AS_OF)
    bars = loaded.candles.load(iid(loaded, "TCS-EQ"), Interval.D1, end=day)
    distance = 1 - bars["close"].iloc[-1] / bars["high"].tail(252).max()  # TCS's own distance from its high
    inside = got_near(loaded, day, "52w", distance + 1e-9)["IT"][1]
    outside = got_near(loaded, day, "52w", distance - 1e-9)["IT"][1]
    assert inside == outside + 1 or distance == 0


def test_bad_close_or_missing_high_is_left_out(loaded):
    day = loaded.breadth.repo.latest_session(AS_OF)
    set_bar(loaded, "RELIANCE-EQ", day, close=float("nan"))
    assert got_near(loaded, day, "52w", 0.10)["Other"][0] == 1  # only HDFCBANK has a usable bar that day


def test_sectors_report_near_high_and_refresh_ath_on_read(loaded):
    out = loaded.breadth.sectors("nifty500", AS_OF, near_pct=10, near_basis="ath")
    assert out["near_pct"] == 10 and out["near_basis"] == "ath"
    day = loaded.breadth.repo.latest_session(AS_OF)
    exp = expected_near(loaded, day, "ath", 0.10)
    assert {s["industry"]: (s["near_high"]["stocks"], s["near_high"]["near"]) for s in out["sectors"]} == exp

    # A bar fetched after the last refresh is picked up before the next read.
    new_day = datetime(2025, 1, 1)
    last = loaded.candles.load(iid(loaded, "TCS-EQ"), Interval.D1).iloc[[-1]]
    last.index = pd.DatetimeIndex([new_day], name="ts")
    loaded.candles.upsert(iid(loaded, "TCS-EQ"), Interval.D1, last, "test")
    loaded.breadth.sectors("nifty500", datetime(2025, 1, 1, 23, 59), near_basis="ath")
    assert new_day in set(stored_ath(loaded).query("instrument_id == @iid(@loaded, 'TCS-EQ')")["ts"])


def test_rotation_by_near_high(loaded):
    ago = {"n": 2, "unit": "w"}
    out = loaded.breadth.rotation("nifty500", AS_OF, ago=ago, min_stocks=1, rank_by="near_high",
                                  near_pct=10, near_basis="52w")
    assert out["rank_by"] == "near_high" and len(out["sectors"]) == 2
    day = loaded.breadth.repo.latest_session(AS_OF)
    frame = loaded.breadth.repo.near_high("nifty500", "52w", 0.10, day - pd.Timedelta(days=60), day)
    sessions = pd.DatetimeIndex(sorted(frame["ts"].unique()))[-(10 + ROTATION_WINDOW):]
    expected = rotation_rows(frame, sessions, 10, ROTATION_WINDOW, 1)[0]
    assert [s["industry"] for s in out["sectors"]] == expected["industry"].tolist()
    assert [s["rank_now"] for s in out["sectors"]] == pytest.approx(expected["rank_now"].tolist())
    assert [s["share_now"] for s in out["sectors"]] == pytest.approx(expected["share_now"].tolist())


def test_bad_near_high_settings_are_rejected(loaded):
    for kwargs in ({"near_basis": "1y"}, {"near_pct": 0}, {"near_pct": 100}):
        with pytest.raises(ValueError):
            loaded.breadth.sectors("nifty500", AS_OF, **kwargs)
    with pytest.raises(ValueError):
        loaded.breadth.rotation("nifty500", AS_OF, rank_by="price")


def test_near_high_api(loaded):
    with TestClient(create_app(loaded)) as client:
        ok = client.get("/api/market/sector-breadth",
                        params={"as_of": "2024-06-28", "near_pct": 5, "near_basis": "ath"})
        assert ok.status_code == 200 and all(s["near_high"] for s in ok.json()["sectors"])
        rot = client.get("/api/market/sector-rotation", params={
            "as_of": "2024-06-28", "rank_by": "near_high", "near_basis": "52w", "min_stocks": 1})
        assert rot.status_code == 200 and rot.json()["rank_by"] == "near_high"
        assert client.get("/api/market/sector-breadth", params={"near_basis": "x"}).status_code == 422
        assert client.get("/api/market/sector-rotation", params={"rank_by": "x"}).status_code == 422
        assert client.post("/api/jobs/highs", params={"rebuild": True}).json()["rows"] > 0

from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import Interval
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


def expected_above(c, period):
    """Sector -> (stocks, above) from pandas, using all available bars when fewer than `period`."""
    out = {}
    for sym in STOCKS:
        iid = c.instruments.find("NSE", sym).instrument_id
        bars = c.candles.load(iid, Interval.D1, end=AS_OF)
        sma = bars["close"].rolling(period, min_periods=1).mean()
        sector = "IT" if sym in ("TCS-EQ", "INFY-EQ") else "Other"
        stocks, above = out.get(sector, (0, 0))
        out[sector] = (stocks + 1, above + int(bars["close"].iloc[-1] > sma.iloc[-1]))
    return out


def test_sql_breadth_matches_pandas(loaded):
    repo = loaded.breadth.repo
    day = repo.latest_session(AS_OF)
    df = repo.compute("nifty500", [10, 20, 300], day, day)  # 300 > bars available in the window
    assert set(df["industry"]) == {"IT", "Other"} and (df["ts"] == day).all()
    for period in (10, 20, 300):
        got = {r.industry: (r.stocks, r.above) for r in df[df["ma_period"] == period].itertuples()}
        assert got == expected_above(loaded, period)


def test_sectors_store_on_first_read_and_compute_other_periods_live(loaded):
    out = loaded.breadth.sectors("nifty500", AS_OF, periods=[20, 15])
    assert out["as_of"].startswith("2024-06-28") and out["periods"] == [15, 20]
    assert {s["industry"] for s in out["sectors"]} == {"IT", "Other"}
    exp = expected_above(loaded, 20)
    assert {s["industry"]: (s["stocks"], s["above"]["20"]) for s in out["sectors"]} == exp
    # sorted by share above the longest period, largest first
    shares = [s["above"]["20"] / s["stocks"] for s in out["sectors"]]
    assert shares == sorted(shares, reverse=True)

    stored = loaded.db.cursor().execute(
        "SELECT DISTINCT ma_period FROM sector_breadth WHERE universe = 'nifty500'").fetchall()
    assert stored == [(20,)]  # 15 is not a stored period


def test_backfill_and_daily_update_store_history(loaded):
    rows = loaded.breadth.backfill()
    days = loaded.db.cursor().execute(
        "SELECT count(DISTINCT ts) FROM sector_breadth WHERE universe = 'all' AND ma_period = 10").fetchone()[0]
    assert rows > 0 and days > 400  # ~2 years of sessions

    report = loaded.daily_update.run(sync_instruments=False, sync_watchlists=False)
    assert not [e for e in report.errors if "breadth" in e]


def test_sector_members_via_scan_run(loaded):
    sma = {"type": "indicator", "name": "sma", "params": {"period": 20}, "output": "sma"}
    out = loaded.screener.run({"type": "group", "match": "all", "items": []}, "nifty500", AS_OF,
                              industry="IT", columns=[sma])
    assert {r["symbol"] for r in out["rows"]} == {"TCS-EQ", "INFY-EQ"}
    assert all(r["sma(20)"] is not None for r in out["rows"])


def test_sector_breadth_api(loaded):
    with TestClient(create_app(loaded)) as client:
        ok = client.get("/api/market/sector-breadth",
                        params={"universe": "nifty500", "as_of": "2024-06-28", "periods": [10, 20]})
        assert ok.status_code == 200 and len(ok.json()["sectors"]) == 2
        assert client.get("/api/market/sector-breadth", params={"periods": [0]}).status_code == 422
        assert client.post("/api/jobs/breadth").json()["rows"] >= 0


# --- sector rotation -------------------------------------------------------------------------

SESSIONS = pd.bdate_range("2024-01-01", periods=10)


def breadth_frame(days, shares, stocks=10):
    """Rows (ts, industry, stocks, above) with `shares[sector][i]` stocks above on days[i]."""
    rows = [{"ts": d, "industry": s, "stocks": (stocks[s] if isinstance(stocks, dict) else stocks), "above": a}
            for s, values in shares.items() for d, a in zip(days, values) if a is not None]
    return pd.DataFrame(rows)


def by_sector(rows):
    return rows.set_index("industry")


def test_rotation_reference_values():
    # then (first 5 days): A 9, B 5, C 1 above -> ranks 1, 2, 3; now (last 5): C 9, A 5, B 1 -> 1, 2, 3
    frame = breadth_frame(SESSIONS, {"A": [9] * 5 + [5] * 5, "B": [5] * 5 + [1] * 5, "C": [1] * 5 + [9] * 5})
    rows, hidden = rotation_rows(frame, SESSIONS, lag=5, window=5, min_stocks=5)
    assert hidden == 0
    assert list(rows["industry"]) == ["C", "A", "B"]  # by change, then the better current rank
    r = by_sector(rows)
    assert r.loc["C", ["rank_then", "rank_now", "rank_change"]].tolist() == [3, 1, 2]
    assert r.loc["A", ["rank_then", "rank_now", "rank_change"]].tolist() == [1, 2, -1]
    assert r.loc["A", "share_then"] == pytest.approx(0.9) and r.loc["A", "share_now"] == pytest.approx(0.5)


def test_rotation_averages_daily_ranks_and_shares_ties():
    # A and B tie every 'now' day (rank 1.5); on 'then' days A leads on 3 of 5 days
    frame = breadth_frame(SESSIONS, {"A": [9, 9, 9, 1, 1, 5, 5, 5, 5, 5], "B": [1, 1, 1, 9, 9, 5, 5, 5, 5, 5]})
    r = by_sector(rotation_rows(frame, SESSIONS, lag=5, window=5, min_stocks=1)[0])
    assert r.loc["A", "rank_then"] == pytest.approx(1.4) and r.loc["B", "rank_then"] == pytest.approx(1.6)
    assert r.loc["A", "rank_now"] == r.loc["B", "rank_now"] == 1.5
    assert r.loc["A", "rank_change"] == pytest.approx(-0.1)


def test_rotation_flat_breadth_has_no_change():
    frame = breadth_frame(SESSIONS, {"A": [5] * 10, "B": [5] * 10})
    rows, _ = rotation_rows(frame, SESSIONS, lag=5, window=5, min_stocks=1)
    assert rows["rank_change"].tolist() == [0, 0] and rows["rank_now"].tolist() == [1.5, 1.5]


def test_rotation_min_stocks_hides_small_sectors_and_new_sectors_sort_last():
    shares = {"A": [9] * 10, "B": [1] * 10, "Small": [3] * 10, "New": [None] * 5 + [5] * 5}
    frame = breadth_frame(SESSIONS, shares, stocks={"A": 10, "B": 10, "Small": 3, "New": 10})
    rows, hidden = rotation_rows(frame, SESSIONS, lag=5, window=5, min_stocks=5)
    assert hidden == 1 and "Small" not in set(rows["industry"])  # not shown and not ranked
    r = by_sector(rows)
    assert r.loc["A", "rank_then"] == 1 and r.loc["B", "rank_then"] == 2  # Small (100%) never ranked
    assert rows["industry"].iloc[-1] == "New"
    assert pd.isna(r.loc["New", "rank_then"]) and pd.isna(r.loc["New", "rank_change"])
    assert r.loc["New", "rank_now"] == 2 and r.loc["B", "rank_now"] == 3  # New ranks among the rest now


def test_rotation_gaps_unsorted_rows_and_overlapping_windows():
    # B has no row on one 'now' day: its averages use the days it was ranked
    shares = {"A": [9] * 10, "B": [1] * 7 + [None, 1, 1], "C": [5] * 10}
    frame = breadth_frame(SESSIONS, shares).sample(frac=1, random_state=1)  # unsorted
    r = by_sector(rotation_rows(frame, SESSIONS, lag=5, window=5, min_stocks=1)[0])
    assert r.loc["B", "rank_now"] == 3 and r.loc["C", "rank_now"] == 2
    # lag shorter than the window: 'then' = the 5 sessions ending one session back
    shares = {"A": [9] * 9 + [1], "B": [5] * 10}
    rows = rotation_rows(breadth_frame(SESSIONS, shares), SESSIONS[-6:], lag=1, window=5, min_stocks=1)[0]
    r = by_sector(rows)
    assert r.loc["A", "rank_then"] == 1 and r.loc["A", "rank_now"] == pytest.approx(1.2)
    assert r.loc["B", "rank_change"] == pytest.approx(0.2)


def test_rotation_service_stored_live_and_unbackfilled(loaded):
    ago = {"n": 2, "unit": "w"}
    # Not backfilled yet: stored period 20 has only the written-through last day, so it falls back to live
    live = loaded.breadth.rotation("nifty500", AS_OF, 20, ago, min_stocks=1)
    loaded.breadth.backfill()
    stored = loaded.breadth.rotation("nifty500", AS_OF, 20, ago, min_stocks=1)
    assert live["sectors"] == stored["sectors"] and len(stored["sectors"]) == 2
    assert stored["as_of"].startswith("2024-06-28") and stored["window"] == ROTATION_WINDOW
    assert stored["windows"]["now"][1] == stored["as_of"]
    assert {s["industry"] for s in stored["sectors"]} == {"IT", "Other"}
    for s in stored["sectors"]:
        assert 1 <= s["rank_now"] <= 2 and s["rank_change"] == pytest.approx(s["rank_then"] - s["rank_now"])

    # Same numbers as the pure function over the SQL breadth for those sessions
    repo = loaded.breadth.repo
    day = repo.latest_session(AS_OF)
    frame = repo.compute("nifty500", [20], day - pd.Timedelta(days=60), day)
    sessions = pd.DatetimeIndex(sorted(frame["ts"].unique()))[-(10 + ROTATION_WINDOW):]
    expected = rotation_rows(frame, sessions, 10, ROTATION_WINDOW, 1)[0]
    assert [s["industry"] for s in stored["sectors"]] == expected["industry"].tolist()
    assert [s["rank_now"] for s in stored["sectors"]] == pytest.approx(expected["rank_now"].tolist())

    # A period that isn't stored is computed live; default min stocks hides both small sectors
    other = loaded.breadth.rotation("nifty500", AS_OF, 15, ago)
    assert other["sectors"] == [] and other["hidden"] == 2


def test_rotation_service_rejects_bad_input_and_short_history(loaded):
    for ago in ({"n": 0, "unit": "w"}, {"n": 13, "unit": "m"}, {"n": 1, "unit": "y"}, {"n": 1.5, "unit": "d"}):
        with pytest.raises(ValueError):
            loaded.breadth.rotation("nifty500", AS_OF, 20, ago)
    with pytest.raises(ValueError):
        loaded.breadth.rotation("nifty500", AS_OF, 0)
    with pytest.raises(ValueError, match="needs 26 sessions"):  # history starts 2023-01-02
        loaded.breadth.rotation("nifty500", datetime(2023, 1, 20, 23, 59), 20, {"n": 1, "unit": "m"}, 1)
    empty = loaded.breadth.rotation("nifty500", datetime(2020, 1, 1), 20)
    assert empty["as_of"] is None and empty["sectors"] == []


def test_sector_rotation_api(loaded):
    with TestClient(create_app(loaded)) as client:
        ok = client.get("/api/market/sector-rotation", params={
            "universe": "nifty500", "as_of": "2024-06-28", "period": 20, "ago_n": 1, "ago_unit": "m", "min_stocks": 1})
        assert ok.status_code == 200
        body = ok.json()
        assert body["ago"] == {"n": 1, "unit": "m"} and len(body["sectors"]) == 2
        assert client.get("/api/market/sector-rotation", params={"ago_n": 0}).status_code == 422
        assert client.get("/api/market/sector-rotation", params={"ago_unit": "y"}).status_code == 422

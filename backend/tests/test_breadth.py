from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import Interval

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

"""Your own watchlists: create/rename/delete, add/remove stocks (no duplicates, kept in the order
added), last stored quotes, and the API around them."""
import math

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import Interval


def _id(container, symbol):
    return container.instruments.find("NSE", symbol).instrument_id


def _store(container, instrument_id, closes, dates=None):
    """Daily bars with the given closes (open = high = low = close)."""
    dates = dates or pd.bdate_range("2026-11-02", periods=len(closes))
    df = pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1000.0},
                      index=pd.DatetimeIndex(dates, name="ts"))
    container.candles.upsert(instrument_id, Interval.D1, df, source="test")


def test_create_and_list_in_name_order(container):
    repo = container.watchlists
    b = repo.create_manual("  Breakouts ")
    a = repo.create_manual("aces")
    assert b["name"] == "Breakouts"  # trimmed
    assert [w["name"] for w in repo.manual_lists()] == ["aces", "Breakouts"]  # case-insensitive order
    assert all(w["member_ids"] == [] for w in repo.manual_lists())
    assert a["watchlist_id"] != b["watchlist_id"]


@pytest.mark.parametrize("name", ["", "   ", "x" * 61, "breakouts", " BREAKOUTS "])
def test_bad_or_duplicate_names_are_refused(container, name):
    container.watchlists.create_manual("Breakouts")
    with pytest.raises(ValueError):
        container.watchlists.create_manual(name)
    assert len(container.watchlists.manual_lists()) == 1


def test_members_keep_the_order_added_and_never_duplicate(container):
    repo = container.watchlists
    wl = repo.create_manual("Swing")["watchlist_id"]
    tcs, infy, rel = _id(container, "TCS-EQ"), _id(container, "INFY-EQ"), _id(container, "RELIANCE-EQ")

    assert repo.add_member(wl, tcs) and repo.add_member(wl, infy) and repo.add_member(wl, rel)
    assert repo.add_member(wl, infy) is False  # already there: no change
    assert repo.manual_lists()[0]["member_ids"] == [tcs, infy, rel]

    assert repo.remove_member(wl, tcs) is True
    assert repo.remove_member(wl, tcs) is False  # not there any more
    assert repo.add_member(wl, tcs)  # re-added: goes to the end
    assert repo.manual_lists()[0]["member_ids"] == [infy, rel, tcs]
    assert repo.member_ids(wl) == sorted([infy, rel, tcs])  # current members, as universes see them


def test_a_stock_can_sit_in_several_lists(container):
    repo = container.watchlists
    a, b = repo.create_manual("A")["watchlist_id"], repo.create_manual("B")["watchlist_id"]
    tcs = _id(container, "TCS-EQ")
    repo.add_member(a, tcs)
    repo.add_member(b, tcs)
    repo.remove_member(a, tcs)
    assert {w["name"]: w["member_ids"] for w in repo.manual_lists()} == {"A": [], "B": [tcs]}


def test_unknown_lists_instruments_and_nse_lists_cannot_be_edited(container):
    container.watchlist_sync.sync_all()
    repo = container.watchlists
    wl = repo.create_manual("Mine")["watchlist_id"]
    tcs = _id(container, "TCS-EQ")
    with pytest.raises(KeyError):
        repo.add_member(wl, 999_999)
    for call in (lambda: repo.add_member("nifty500", tcs), lambda: repo.remove_member("nifty500", tcs),
                 lambda: repo.rename_manual("nifty500", "x"), lambda: repo.delete_manual("nifty500"),
                 lambda: repo.add_member("nope", tcs), lambda: repo.delete_manual("nope")):
        with pytest.raises(KeyError):
            call()
    assert tcs in repo.member_ids("nifty500")
    assert [w["name"] for w in repo.manual_lists()] == ["Mine"]  # NSE lists aren't "yours"


def test_rename_and_delete(container):
    repo = container.watchlists
    a = repo.create_manual("Alpha")["watchlist_id"]
    repo.create_manual("Beta")
    repo.rename_manual(a, "ALPHA")  # changing only the case of its own name is fine
    with pytest.raises(ValueError):
        repo.rename_manual(a, "beta")
    repo.add_member(a, _id(container, "TCS-EQ"))
    repo.delete_manual(a)
    assert [w["name"] for w in repo.manual_lists()] == ["Beta"]
    left = container.db.cursor().execute(
        "SELECT count(*) FROM watchlist_members WHERE watchlist_id = ?", [a]).fetchone()[0]
    assert left == 0


def test_nse_sync_leaves_your_lists_alone(container):
    repo = container.watchlists
    wl = repo.create_manual("Mine")["watchlist_id"]
    tcs = _id(container, "TCS-EQ")
    repo.add_member(wl, tcs)
    container.watchlist_sync.sync_all()
    assert repo.manual_lists() == [{"watchlist_id": wl, "name": "Mine", "member_ids": [tcs]}]


def test_nightly_update_fetches_your_list_members(container):
    container.watchlists.add_member(container.watchlists.create_manual("Mine")["watchlist_id"],
                                    _id(container, "TCS-EQ"))
    report = container.daily_update.run(sync_instruments=False, sync_watchlists=False)
    assert report.targets == 1 and report.ok == 1
    assert not container.candles.load(_id(container, "TCS-EQ"), Interval.D1).empty


def test_latest_quotes_reference_values_and_edge_cases(container):
    market = container.market
    tcs, infy, rel, hdfc = (_id(container, s) for s in ("TCS-EQ", "INFY-EQ", "RELIANCE-EQ", "HDFCBANK-EQ"))
    # Stored out of order: the latest is still the last by date.
    _store(container, tcs, [100.0, 110.0], ["2026-11-03", "2026-11-02"])
    _store(container, tcs, [121.0], ["2026-11-04"])
    _store(container, infy, [50.0])  # only one bar: no change
    _store(container, rel, [0.0, 10.0])  # zero previous close: no change
    _store(container, hdfc, [10.0, float("nan")])  # bad last close

    quotes = market.latest_quotes([tcs, infy, rel, hdfc, _id(container, "Nifty 50")])
    assert quotes[tcs]["close"] == 121.0 and math.isclose(quotes[tcs]["pct_change"], 0.21)  # vs 100 on 3 Nov
    assert str(quotes[tcs]["ts"]).startswith("2026-11-04")
    assert quotes[infy] == {**quotes[infy], "close": 50.0, "pct_change": None}
    assert quotes[rel]["close"] == 10.0 and quotes[rel]["pct_change"] is None
    assert quotes[hdfc]["close"] is None and quotes[hdfc]["pct_change"] is None
    assert _id(container, "Nifty 50") not in quotes  # nothing stored
    assert market.latest_quotes([]) == {}


def test_api_round_trip(container):
    tcs, infy = _id(container, "TCS-EQ"), _id(container, "INFY-EQ")
    _store(container, infy, [100.0, 105.0])
    with TestClient(create_app(container)) as client:
        assert client.get("/api/watchlists/mine").json() == []
        wl = client.post("/api/watchlists/mine", json={"name": "Swing"}).json()
        wid = wl["watchlist_id"]
        assert wl == {"watchlist_id": wid, "name": "Swing", "member_ids": []}
        assert client.post("/api/watchlists/mine", json={"name": "swing"}).status_code == 422

        assert client.put(f"/api/watchlists/mine/{wid}/members/{infy}").json() == {"added": True}
        assert client.put(f"/api/watchlists/mine/{wid}/members/{tcs}").json() == {"added": True}
        assert client.put(f"/api/watchlists/mine/{wid}/members/{infy}").json() == {"added": False}
        assert client.put(f"/api/watchlists/mine/{wid}/members/999999").status_code == 404
        assert client.put(f"/api/watchlists/mine/nope/members/{tcs}").status_code == 404

        rows = client.get(f"/api/watchlists/mine/{wid}/quotes").json()
        assert [r["symbol"] for r in rows] == ["INFY-EQ", "TCS-EQ"]  # order added
        assert rows[0]["close"] == 105.0 and math.isclose(rows[0]["pct_change"], 0.05)
        assert rows[1]["close"] is None and rows[1]["ts"] is None  # no bars stored yet
        assert client.get("/api/watchlists/mine/nope/quotes").status_code == 404

        assert client.patch(f"/api/watchlists/mine/{wid}", json={"name": "Swing ideas"}).status_code == 200
        assert client.patch(f"/api/watchlists/mine/{wid}", json={"name": " "}).status_code == 422
        assert client.patch("/api/watchlists/mine/nope", json={"name": "x"}).status_code == 404
        assert client.delete(f"/api/watchlists/mine/{wid}/members/{tcs}").json() == {"removed": True}
        assert client.get("/api/watchlists/mine").json() == [
            {"watchlist_id": wid, "name": "Swing ideas", "member_ids": [infy]}]

        assert client.delete(f"/api/watchlists/mine/{wid}").status_code == 200
        assert client.delete(f"/api/watchlists/mine/{wid}").status_code == 404
        assert client.get("/api/watchlists/mine").json() == []

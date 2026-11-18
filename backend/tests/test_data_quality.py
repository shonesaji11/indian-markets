from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import Interval
from markets.engine.data_quality import (
    find_bad_bars,
    find_gaps,
    find_jumps,
    find_short_history,
    find_stale,
    trading_sessions,
)

S = pd.bdate_range("2024-01-01", periods=8)  # sessions S[0]..S[7]


def bars(rows, kind="EQ"):
    """Rows of (instrument_id, ts, open, high, low, close, volume)."""
    df = pd.DataFrame(rows, columns=["instrument_id", "ts", "open", "high", "low", "close", "volume"])
    df["instrument_type"] = kind
    return df


def bar(iid, ts, close=100.0, volume=1000.0, high=None, low=None):
    return (iid, ts, close, close + 1 if high is None else high, close - 1 if low is None else low, close, volume)


# --- engine ---------------------------------------------------------------------------------


def test_trading_sessions_drop_stray_days():
    counts = pd.Series([100, 98, 2, 101], index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-06", "2024-01-08"]))
    assert list(trading_sessions(counts)) == list(pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-08"]))
    assert trading_sessions(pd.Series(dtype="int64")).empty


def test_gaps_reference_and_edges():
    df = bars([bar(1, S[0]), bar(1, S[1]), bar(1, S[4]), bar(1, S[5]), bar(1, S[5]),  # duplicate bar
               bar(2, S[3]), bar(2, S[2]), bar(2, S[7]),                                  # unsorted
               bar(3, S[6]),                                                              # single bar
               bar(1, pd.Timestamp("2024-01-06"))])                                       # a Saturday: not a session
    gaps = find_gaps(df, S).sort_values(["instrument_id", "start_ts"]).reset_index(drop=True)
    assert gaps[["instrument_id", "start_ts", "end_ts"]].values.tolist() == [[1, S[2], S[3]], [2, S[4], S[6]]]
    assert gaps["detail"].tolist() == ["2 sessions with no bar", "3 sessions with no bar"]
    assert find_gaps(bars([]), S).empty


def test_bad_bars():
    df = bars([bar(1, S[0]), bar(1, S[1], close=0), bar(1, S[2], volume=0), bar(1, S[3], high=90, low=95),
               (1, S[4], 100, 101, 99, np.nan, np.nan)])
    out = find_bad_bars(df).set_index("start_ts")["detail"]
    assert out.to_dict() == {S[1]: "missing or zero price", S[2]: "no volume", S[3]: "high below low",
                             S[4]: "missing or zero price, no volume"}
    assert find_bad_bars(bars([bar(9, S[0], volume=0)], kind="INDEX")).empty  # index volume is always 0


def test_jumps():
    df = bars([bar(1, S[2], 150), bar(1, S[0], 100), bar(1, S[1], 100), bar(1, S[3], 130),  # +50%, then -13%
               bar(2, S[0], 100), bar(2, S[1], 0), bar(2, S[2], 100)])                       # zero close: a bad bar, not a jump
    out = find_jumps(df)
    assert out[["instrument_id", "start_ts", "detail"]].values.tolist() == [[1, S[2], "close +50% vs previous bar"]]
    assert find_jumps(bars([bar(9, S[0], 100), bar(9, S[1], 200)], kind="INDEX")).empty
    assert find_jumps(bars([bar(1, S[0], 100), bar(1, S[1], 134)])).empty  # under the threshold


def test_stale_and_short_history():
    last = pd.Series({1: S[7], 2: S[4], 3: S[3]})
    out = find_stale(last, S)
    assert out[["instrument_id", "detail"]].values.tolist() == [[3, "no bar for the last 4 sessions"]]  # 2 is 3 behind: ok
    short = find_short_history(pd.Series({1: 250, 2: 30}), pd.Series({1: S[0], 2: S[5]}))
    assert short[["instrument_id", "start_ts", "detail"]].values.tolist() == [[2, S[5], "30 bars, fewer than 200"]]


# --- service ---------------------------------------------------------------------------------

STOCKS = ("RELIANCE-EQ", "TCS-EQ", "INFY-EQ", "HDFCBANK-EQ")


@pytest.fixture
def loaded(container):
    container.watchlist_sync.sync_all()
    for ref in (*STOCKS, "Nifty 50"):
        iid = container.instruments.find("NSE", ref).instrument_id
        container.ingestion.ingest(iid, Interval.D1, datetime(2023, 1, 1), datetime(2024, 6, 28))
    return container


def iid(c, symbol):
    return c.instruments.find("NSE", symbol).instrument_id


def open_issues(c, check):
    return c.data_quality.report("open", check)["issues"]


def test_full_then_incremental_gap_found_and_resolved(loaded):
    c, tcs = loaded, iid(loaded, "TCS-EQ")
    first = c.data_quality.run()
    assert first["mode"] == "full" and first["instruments_rechecked"] == 5
    assert c.data_quality.run()["instruments_rechecked"] == 0  # nothing new since

    day = pd.Timestamp("2024-03-14")
    c.db.cursor().execute("DELETE FROM candles WHERE instrument_id = ? AND ts = ?", [tcs, day])
    assert c.data_quality.run()["checks"].get("gap") is None  # a deletion isn't new data: incremental can't see it
    full = c.data_quality.run(full=True)
    assert full["checks"]["gap"]["new"] == 1
    gap = open_issues(c, "gap")[0]
    assert (gap["symbol"], pd.Timestamp(gap["start_ts"]), gap["detail"]) == ("TCS-EQ", day, "1 session with no bar")

    c.ingestion.ingest(tcs, Interval.D1, datetime(2024, 3, 1), datetime(2024, 3, 31))  # re-download fills it
    again = c.data_quality.run()
    assert again["mode"] == "incremental" and again["instruments_rechecked"] == 1
    assert again["checks"]["gap"]["resolved"] == 1 and open_issues(c, "gap") == []


def test_bad_bar_accept_and_reopen(loaded):
    c, infy = loaded, iid(loaded, "INFY-EQ")
    c.data_quality.run()
    c.db.cursor().execute("UPDATE candles SET close = 0, ingested_at = current_timestamp + INTERVAL 1 MINUTE "
                          "WHERE instrument_id = ? AND ts = '2024-02-01'", [infy])
    out = c.data_quality.run()
    assert out["checks"]["bad_bar"]["new"] == 1
    issue = open_issues(c, "bad_bar")[0]["issue_id"]
    with pytest.raises(ValueError):
        c.data_quality.accept(issue, " ")
    assert c.data_quality.accept(issue, "checked on NSE: real zero print")
    c.data_quality.run(full=True)
    assert open_issues(c, "bad_bar") == []  # still found, but stays accepted
    assert c.data_quality.report("accepted", "bad_bar")["issues"][0]["seen_count"] == 2


def test_global_checks_and_scoped_runs(loaded):
    c, infy, rel = loaded, iid(loaded, "INFY-EQ"), iid(loaded, "RELIANCE-EQ")
    c.db.cursor().execute("DELETE FROM candles WHERE instrument_id = ? AND ts > '2024-06-20'", [infy])
    c.db.cursor().execute("DELETE FROM candles WHERE instrument_id = ? AND ts < '2024-01-01'", [rel])
    c.db.cursor().execute(
        "INSERT INTO ingestion_runs VALUES ('r1', 'fake', ?, '1d', '2024-01-01', '2024-06-28', 'error', NULL, "
        "'Access denied because of exceeding access rate', current_timestamp + INTERVAL 1 HOUR, NULL)", [infy])
    out = c.data_quality.run()
    assert [i["symbol"] for i in open_issues(c, "stale")] == ["INFY-EQ"]
    assert [i["symbol"] for i in open_issues(c, "failed_download")] == ["INFY-EQ"]
    assert open_issues(c, "short_history") == []  # recorded as expected (accepted), not open
    assert [i["symbol"] for i in c.data_quality.report("accepted", "short_history")["issues"]] == ["RELIANCE-EQ"]
    assert out["checks"]["short_history"]["found"] == 1

    # A later successful download resolves the failure; a scoped run doesn't move the watermark.
    c.db.cursor().execute(
        "INSERT INTO ingestion_runs VALUES ('r2', 'fake', ?, '1d', '2024-06-20', '2024-06-28', 'ok', 5, NULL, "
        "current_timestamp + INTERVAL 2 HOUR, NULL)", [infy])
    mark = c.data_quality.repo.get_state("watermark")
    scoped = c.data_quality.run(checks=["failed_download"], instrument_ids=[infy])
    assert scoped["checks"]["failed_download"]["resolved"] == 1
    assert c.data_quality.repo.get_state("watermark") == mark
    with pytest.raises(ValueError, match="unknown check"):
        c.data_quality.run(checks=["nope"])


def test_version_change_forces_full_run(loaded):
    c = loaded
    c.data_quality.run()
    c.data_quality.repo.set_state("version", "0")
    assert c.data_quality.run()["mode"] == "full"


def test_api_and_nightly_hook(loaded):
    c = loaded
    with TestClient(create_app(c)) as client:
        run = client.post("/api/dq/check", json={"instruments": ["NSE:TCS-EQ"], "checks": ["gap"]}).json()
        assert run["instruments_rechecked"] == 1
        assert client.post("/api/dq/check", json={"checks": ["nope"]}).status_code == 422
        report = client.get("/api/dq/issues", params={"status": "all"}).json()
        assert {"counts", "issues"} <= set(report)
        assert client.post("/api/dq/issues/nope/accept", json={"note": "x"}).status_code == 404
        assert client.get("/api/dq/issues", params={"instrument": "NSE:NOPE"}).status_code == 404
    report = c.daily_update.run(sync_instruments=False, sync_watchlists=False)
    assert report.data_quality is not None and report.data_quality["mode"] in ("full", "incremental")

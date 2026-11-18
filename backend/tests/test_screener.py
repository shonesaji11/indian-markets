from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import Interval
from markets.engine import default_registry
from markets.engine.screener import bars_ago, evaluate, indicator_frame, operand_key, operand_label, validate

STOCKS = ("RELIANCE-EQ", "TCS-EQ", "INFY-EQ", "HDFCBANK-EQ")


def field(name):
    return {"type": "field", "field": name}


def value(v):
    return {"type": "value", "value": v}


def cond(left, op, right):
    return {"type": "condition", "left": left, "op": op, "right": right}


def group(match, *items):
    return {"type": "group", "match": match, "items": list(items)}


def series(**by_id):
    return pd.Series(by_id, dtype="float64")


def test_evaluate_nested_and_or_with_percent_and_crossovers():
    index = pd.Index(["a", "b", "c"])
    values = {
        "close": (series(a=110, b=90, c=105), series(a=95, b=105, c=101)),
        "high_52w": (series(a=100, b=100, c=100), series(a=100, b=100, c=100)),
        "pct_change": (series(a=0.03, b=-0.01, c=float("nan")), series(a=0, b=0, c=0)),
    }
    # close > 52w high AND (change > 2% OR close crossed above 52w high today)
    tree = group("all",
                 cond(field("close"), "gt", field("high_52w")),
                 group("any",
                       cond(field("pct_change"), "gt", value(2)),
                       cond(field("close"), "crosses_above", field("high_52w"))))
    assert evaluate(tree, values, index).tolist() == [True, False, False]  # c: NaN change, already above yesterday
    assert evaluate(group("all"), values, index).all()  # empty group matches everything
    assert evaluate(cond(field("close"), "crosses_below", field("high_52w")), values, index).tolist() == [False, True, False]


def test_validate_rejects_bad_trees():
    registry = default_registry()
    validate(group("all", cond({"type": "indicator", "name": "macd", "params": {"fast": 8}, "output": "signal"},
                               "gt", value(0))), registry)
    for bad in (group("both"),
                group("all", cond(field("nope"), "gt", value(1))),
                group("all", cond(field("close"), "eq", value(1))),
                group("all", cond({"type": "indicator", "name": "nope"}, "gt", value(1))),
                group("all", cond({"type": "indicator", "name": "rsi", "params": {"window": 3}}, "gt", value(1)))):
        with pytest.raises(ValueError):
            validate(bad, registry)


def test_operand_labels():
    assert operand_label(field("pct_change")) == "Change %"
    assert operand_label({"type": "indicator", "name": "sma", "params": {"period": 20, "source": "close"},
                          "output": "sma"}) == "SMA 20"
    assert operand_label({"type": "indicator", "name": "macd", "params": {"fast": 12, "slow": 26, "signal": 9},
                          "output": "signal"}) == "MACD signal 12,26,9"


def test_operand_keys_are_readable():
    assert operand_key(field("close")) == "close"
    assert operand_key({"type": "indicator", "name": "rsi", "params": {"period": 14}, "output": "rsi"}) == "rsi(14)"
    assert operand_key({"type": "indicator", "name": "macd", "params": {"fast": 12, "slow": 26, "signal": 9},
                        "output": "signal"}) == "macd.signal(12,26,9)"


def test_indicator_short_history_is_nan_not_a_shorter_window():
    spec = default_registry().get("sma")
    ts = pd.date_range("2024-01-01", periods=5)
    bars = pd.DataFrame({"instrument_id": 1, "ts": ts, "open": 1.0, "high": 1.0, "low": 1.0,
                         "close": [1.0, 2, 3, 4, 5], "volume": 1.0})
    assert indicator_frame(spec, {"period": 20}, "sma", bars)[1].isna().all()
    assert indicator_frame(spec, {"period": 3}, "sma", bars)[1].iloc[-1] == pytest.approx(4.0)


def test_ago_offsets_keys_labels_and_validation():
    sma = {"type": "indicator", "name": "sma", "params": {"period": 20}, "output": "sma"}
    week = {**sma, "ago": {"n": 1, "unit": "w"}}
    assert [bars_ago(sma), bars_ago(week), bars_ago({**sma, "ago": {"n": 2, "unit": "m"}})] == [0, 5, 42]
    assert bars_ago({**sma, "ago": {"n": 0, "unit": "w"}}) == 0
    assert operand_key(week) == "sma(20)@1w" and operand_label(week) == "SMA 20 · 1w ago"
    assert operand_key({**sma, "ago": {"n": 0, "unit": "d"}}) == "sma(20)"  # 0 = today, same as no offset
    assert operand_label(field("close") | {"ago": {"n": 3, "unit": "d"}}) == "Close · 3d ago"
    assert operand_label({"type": "indicator", "name": "adr_pct", "params": {"period": 20}, "output": "adr_pct"}) == "ADR% 20"
    reg = default_registry()
    validate(group("all", cond(sma, "gt", week)), reg)
    validate(group("all", cond(field("close") | {"ago": {"n": 12, "unit": "m"}}, "gt", value(0))), reg)
    for bad in ({"n": 13, "unit": "m"}, {"n": -1, "unit": "d"}, {"n": 1.5, "unit": "d"}, {"n": 1, "unit": "y"}, "1w"):
        with pytest.raises(ValueError, match="ago"):
            validate(group("all", cond(field("close") | {"ago": bad}, "gt", value(0))), reg)


@pytest.fixture
def loaded(container):
    container.watchlist_sync.sync_all()
    for ref in (*STOCKS, "Nifty 50"):
        iid = container.instruments.find("NSE", ref).instrument_id
        container.ingestion.ingest(iid, Interval.D1, datetime(2023, 1, 1), datetime(2024, 12, 31))
    return container


def test_run_matches_pandas_and_handles_indices(loaded):
    rsi = {"type": "indicator", "name": "rsi", "params": {"period": 14}, "output": "rsi"}
    tree = group("any", cond(rsi, "gt", value(50)), cond(field("pct_change"), "gt", value(1)))
    as_of = datetime(2024, 6, 28, 23, 59)
    out = loaded.screener.run(tree, "all", as_of)

    assert out["as_of"].startswith("2024-06-28")
    assert out["universe"]["priced"] == 4  # Nifty 50 excluded by default
    spec = default_registry().get("rsi")
    expected = set()
    for sym in STOCKS:
        c = loaded.candles.load(loaded.instruments.find("NSE", sym).instrument_id, Interval.D1, end=as_of)
        if spec.compute(c, {"period": 14})["rsi"].iloc[-1] > 50 or c["close"].iloc[-1] / c["close"].iloc[-2] - 1 > 0.01:
            expected.add(sym)
    assert {r["symbol"] for r in out["rows"]} == expected
    assert all("rsi(14)" in r for r in out["rows"])
    assert out["columns"][0] == {"key": "rsi(14)", "label": "RSI 14", "percent": False}

    with_indices = loaded.screener.run(group("all"), "all", as_of, include_indices=True)
    assert with_indices["universe"]["priced"] == 5


def test_scans_api_and_saved_scans(loaded):
    with TestClient(create_app(loaded)) as client:
        assert {f["name"] for f in client.get("/api/scans/fields").json()} >= {"close", "pct_change"}

        saved = client.get("/api/scans/saved").json()
        assert [s["name"] for s in saved] == ["At 52-week high"]  # seeded by the migration
        body = {"filter": saved[0]["definition"]["filter"], "universe": "nifty500", "as_of": "2024-06-28"}
        out = client.post("/api/scans/run", json=body).json()
        assert all(r["high_52w"] is not None for r in out["rows"])

        bad = client.post("/api/scans/run", json={"filter": group("all", cond(field("nope"), "gt", value(1)))})
        assert bad.status_code == 422 and "nope" in bad.json()["detail"]

        definition = {"filter": group("all", cond(field("close"), "gt", value(100))), "universe": "all"}
        first = client.post("/api/scans/saved", json={"name": "Above 100", "definition": definition}).json()
        again = client.post("/api/scans/saved", json={"name": "Above 100", "definition": definition}).json()
        assert first == again  # same name replaces
        assert len(client.get("/api/scans/saved").json()) == 2
        assert client.delete(f"/api/scans/saved/{first['scan_id']}").status_code == 200
        assert client.delete(f"/api/scans/saved/{first['scan_id']}").status_code == 404


def test_basket_performance_service_and_api(loaded):
    ids = [loaded.instruments.find("NSE", s).instrument_id for s in ("RELIANCE-EQ", "TCS-EQ")]
    start, end = datetime(2024, 6, 3), datetime(2024, 6, 28, 23, 59)
    out = loaded.screener.performance(ids, start, end)

    expected = {}
    for iid in ids:
        c = loaded.candles.load(iid, Interval.D1, start=start, end=end)
        expected[iid] = c["close"].iloc[-1] / c["open"].iloc[1] - 1  # bought at the open after the pick
    assert out["start"].startswith("2024-06-03") and out["end"].startswith("2024-06-28")
    assert out["total"] == out["counted"] == 2
    assert {s["instrument_id"]: s["change"] for s in out["stocks"]} == pytest.approx(expected)
    assert out["basket"][0]["value"] == 0
    assert out["basket"][-1]["value"] == pytest.approx(sum(expected.values()) / 2)
    assert out["benchmark"]["label"] == "Nifty 50"
    assert [p["ts"] for p in out["benchmark"]["points"]] == [p["ts"] for p in out["basket"]]
    assert out["sessions"] == len(out["basket"]) - 1

    with pytest.raises(ValueError):
        loaded.screener.performance(ids, start, datetime(2024, 5, 1))
    with TestClient(create_app(loaded)) as client:
        body = {"instrument_ids": ids, "start": "2024-06-03", "end": "2024-06-28"}
        assert client.post("/api/scans/performance", json=body).json()["counted"] == 2
        bad = client.post("/api/scans/performance", json={**body, "end": "2024-05-01"})
        assert bad.status_code == 422
        none = client.post("/api/scans/performance", json={"instrument_ids": [], "start": "2024-06-03"}).json()
        assert none["counted"] == 0 and none["basket"] == [] and none["benchmark"] is None


def _expected(loaded, as_of, rule):
    """Stocks for which rule(closes, ts-indexed candles) holds, computed straight from stored candles."""
    out = set()
    for sym in STOCKS:
        c = loaded.candles.load(loaded.instruments.find("NSE", sym).instrument_id, Interval.D1, end=as_of)
        if rule(c):
            out.add(sym)
    return out


def test_ago_offsets_match_pandas(loaded):
    as_of = datetime(2024, 6, 28, 23, 59)
    sma, close = {"type": "indicator", "name": "sma", "params": {"period": 20}, "output": "sma"}, field("close")
    rising = cond(sma, "gt", sma | {"ago": {"n": 1, "unit": "w"}})
    out = loaded.screener.run(group("all", rising), "all", as_of)
    s20 = lambda c: c["close"].rolling(20).mean()
    assert {r["symbol"] for r in out["rows"]} == _expected(loaded, as_of, lambda c: s20(c).iloc[-1] > s20(c).iloc[-6])
    assert {c["key"] for c in out["columns"]} == {"sma(20)", "sma(20)@1w"}
    row = out["rows"][0] if out["rows"] else None
    if row:
        c = loaded.candles.load(row["instrument_id"], Interval.D1, end=as_of)
        assert row["sma(20)@1w"] == pytest.approx(s20(c).iloc[-6])

    # Both sides offset: close 1w ago > close 2w ago; field values come from the earlier sessions.
    both = cond(close | {"ago": {"n": 1, "unit": "w"}}, "gt", close | {"ago": {"n": 2, "unit": "w"}})
    out = loaded.screener.run(group("all", both), "all", as_of)
    assert {r["symbol"] for r in out["rows"]} == _expected(loaded, as_of, lambda c: c["close"].iloc[-6] > c["close"].iloc[-11])

    # Crossover on an earlier session: close crossed above SMA 20 exactly 3 sessions ago.
    cross = cond(close | {"ago": {"n": 3, "unit": "d"}}, "crosses_above", sma | {"ago": {"n": 3, "unit": "d"}})
    out = loaded.screener.run(group("all", cross), "all", as_of)
    x = lambda c: c["close"].iloc[-4] > s20(c).iloc[-4] and c["close"].iloc[-5] <= s20(c).iloc[-5]
    assert {r["symbol"] for r in out["rows"]} == _expected(loaded, as_of, x)


def test_missing_bar_or_short_history_leaves_stock_out(loaded):
    as_of = datetime(2024, 6, 28, 23, 59)
    tcs = loaded.instruments.find("NSE", "TCS-EQ").instrument_id
    day = loaded.market.recent_sessions([tcs], as_of, 6)[5]  # the session 1w before
    loaded.db.cursor().execute("DELETE FROM candles WHERE instrument_id = ? AND timeframe = '1d' AND ts = ?", [tcs, day])
    anything = cond(field("close") | {"ago": {"n": 1, "unit": "w"}}, "gt", value(0))
    out = loaded.screener.run(group("all", anything), "all", as_of)
    assert "TCS-EQ" not in {r["symbol"] for r in out["rows"]} and len(out["rows"]) == 3

    # Data starts 2023-01-01: by mid-Feb there are ~30 bars, too few for SMA 200, so nothing matches.
    sma200 = {"type": "indicator", "name": "sma", "params": {"period": 200}, "output": "sma"}
    early = loaded.screener.run(group("all", cond(sma200, "gt", value(0))), "all", datetime(2023, 2, 15, 23, 59))
    assert early["rows"] == []
    # Too few sessions for the offset also means no match.
    far = cond(field("close") | {"ago": {"n": 12, "unit": "m"}}, "gt", value(0))
    assert loaded.screener.run(group("all", far), "all", datetime(2023, 6, 30, 23, 59))["rows"] == []

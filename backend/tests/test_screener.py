from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import Interval
from markets.engine import default_registry
from markets.engine.screener import evaluate, indicator_values, operand_key, operand_label, validate

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


def test_indicator_uses_available_history_when_short():
    spec = default_registry().get("sma")
    ts = pd.date_range("2024-01-01", periods=5)
    bars = pd.DataFrame({"instrument_id": 1, "ts": ts, "open": 1.0, "high": 1.0, "low": 1.0,
                         "close": [1.0, 2, 3, 4, 5], "volume": 1.0})
    now, prev = indicator_values(spec, {"period": 20}, "sma", bars)
    assert now[1] == pytest.approx(3.0)  # mean of the 5 bars available, not NaN


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
        c = loaded.candles.load(iid, Interval.D1, start=start, end=end)["close"]
        expected[iid] = c.iloc[-1] / c.iloc[0] - 1
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

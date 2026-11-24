"""Train a big-movers model (run once per model version; the result is committed under src/markets/models/).

Reads daily bars of today's Nifty Total Market members, the Nifty 50 and India VIX from the running dashboard
API (read-only), builds the night-before features with `markets.engine.movers.build_features`, fits XGBoost
on 2018-2024 with the settings tuned in the research study (research/movers/ml_co_4.md: depth 6, 600 trees,
min child weight 200) and writes <version>.json (the booster) + <version>.meta.json.

    python scripts/train_movers.py [--api http://127.0.0.1:8000/api] [--bars bars.pkl] [--predict-out p.pkl]

--bars caches the downloaded bars (read if it exists). --predict-out writes test-period (2025-) probabilities,
used to check the model against the research study's predictions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import pandas as pd
import xgboost as xgb

from markets.engine.movers import FEATURE_COLUMNS, FEATURES_VERSION, build_features

VERSION = "co4_eod_v1"
TRAIN = ("2018-01-01", "2024-12-31")
TEST_START = "2025-01-01"
PARAMS = {"objective": "binary:logistic", "max_depth": 6, "min_child_weight": 200, "learning_rate": 0.05,
          "subsample": 0.8, "colsample_bytree": 0.8, "tree_method": "hist", "seed": 0, "nthread": -1,
          "eval_metric": "logloss"}
ROUNDS = 600
OUT_DIR = Path(__file__).resolve().parents[1] / "src" / "markets" / "models"


def fetch_bars(api: str) -> pd.DataFrame:
    def get(path, **params):
        r = httpx.get(f"{api}{path}", params=params, timeout=120)
        r.raise_for_status()
        return r.json()

    members = get("/watchlists/niftytotalmarket/members")
    members = members.get("members", members) if isinstance(members, dict) else members
    ids = {r.get("instrument_id", r.get("id")) for r in members}
    index_ids = {}
    for name in ("Nifty 50", "India VIX"):
        hits = [i for i in get("/instruments", q=name, exchange="NSE", limit=20) if i["symbol"] == name]
        index_ids[name] = hits[0]["instrument_id"]
    frames = []
    for iid in sorted(ids | set(index_ids.values())):
        df = pd.DataFrame(get(f"/candles/{iid}", interval="1d", start="2016-01-01")["candles"])
        if not df.empty:
            frames.append(df.assign(instrument_id=iid))
    bars = pd.concat(frames)[["instrument_id", "ts", "open", "high", "low", "close", "volume"]]
    bars["ts"] = pd.to_datetime(bars["ts"]).dt.normalize()
    return bars.assign(role=bars.instrument_id.map({v: k for k, v in index_ids.items()}).fillna("stock"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000/api")
    ap.add_argument("--bars", type=Path)
    ap.add_argument("--predict-out", type=Path)
    a = ap.parse_args()
    if a.bars and a.bars.exists():
        bars = pd.read_pickle(a.bars)
    else:
        bars = fetch_bars(a.api)
        if a.bars:
            bars.to_pickle(a.bars)
    stocks = bars[bars.role == "stock"]
    feats = build_features(stocks, bars[bars.role == "Nifty 50"], bars[bars.role == "India VIX"])
    X = list(FEATURE_COLUMNS)
    train = feats[(feats.ts >= TRAIN[0]) & (feats.ts <= TRAIN[1])]
    booster = xgb.train(PARAMS, xgb.DMatrix(train[X], label=train.big), num_boost_round=ROUNDS)
    OUT_DIR.mkdir(exist_ok=True)
    booster.save_model(OUT_DIR / f"{VERSION}.json")
    meta = {"version": VERSION, "features_version": FEATURES_VERSION, "features": X, "target": "|close/open-1| >= 4%",
            "train": list(TRAIN), "train_rows": len(train), "train_big_rate": round(float(train.big.mean()), 4),
            "params": PARAMS, "rounds": ROUNDS, "xgboost": xgb.__version__, "stocks": int(stocks.instrument_id.nunique()),
            "bars_until": str(bars.ts.max().date())}
    (OUT_DIR / f"{VERSION}.meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"{VERSION}: {len(train):,} rows, big-move rate {train.big.mean():.2%}")
    if a.predict_out:
        test = feats[feats.ts >= TEST_START].copy()
        test["p"] = booster.predict(xgb.DMatrix(test[X]))
        test[["instrument_id", "ts", "big", "move", "p"]].to_pickle(a.predict_out)


if __name__ == "__main__":
    main()

"""Buy-and-hold performance of a basket of instruments bought at one session's close.

Pure functions over long-format daily closes (`instrument_id, ts, close`). Correcting wrong data
(splits etc.) is the ingestion job's concern; this only copes with data that is real but incomplete:
gaps carry the last close forward, and instruments without a bar after the start are not counted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BasketPerformance:
    # Indexed by instrument_id: every instrument with a close on the start session.
    # `close` = last close in the window; `change` = close / entry - 1 (NaN when not counted).
    stocks: pd.DataFrame
    # Indexed by session ts, from the start session (0.0) on: equal-weight mean change of the counted instruments.
    path: pd.Series
    # Instruments in the mean: a close on the start session and at least one bar after it.
    counted: int


def basket_performance(closes: pd.DataFrame, start: pd.Timestamp) -> BasketPerformance:
    """Each instrument's change from its close on `start`'s session, and the equal-weight basket path."""
    empty = BasketPerformance(pd.DataFrame(columns=["close", "change"]), pd.Series(dtype="float64"), 0)
    df = closes[["instrument_id", "ts", "close"]].copy()
    df["ts"] = pd.to_datetime(df["ts"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df[np.isfinite(df["close"]) & (df["close"] > 0)]
    df = df[df["ts"].dt.normalize() >= pd.Timestamp(start).normalize()]
    df = df.drop_duplicates(["instrument_id", "ts"], keep="last")
    if df.empty:
        return empty

    wide = df.pivot(index="ts", columns="instrument_id", values="close").sort_index()
    if wide.index[0].normalize() != pd.Timestamp(start).normalize():
        return empty  # nothing traded on the start session, so there is no entry price
    entry = wide.iloc[0].dropna()
    wide = wide[entry.index]
    later = wide.iloc[1:].notna().any()
    held = wide.ffill()
    changes = held / entry - 1

    counted = later[later].index
    stocks = pd.DataFrame({"close": held.iloc[-1], "change": changes.iloc[-1].where(later)})
    stocks.index.name = "instrument_id"
    path = changes[counted].mean(axis=1) if len(counted) else pd.Series(dtype="float64")
    return BasketPerformance(stocks, path, len(counted))

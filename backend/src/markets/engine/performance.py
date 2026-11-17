"""Buy-and-hold performance of a basket of instruments picked on one session and bought at the next open.

Pure functions over long-format daily bars (`instrument_id, ts, open, close`). Correcting wrong data
(splits etc.) is the ingestion job's concern; this only copes with data that is real but incomplete:
gaps carry the last close forward, and instruments with no usable bar after the pick are not counted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BasketPerformance:
    # Indexed by instrument_id: every instrument with a close on the pick session. `entry` = open of
    # its first bar after the pick, `close` = last close in the window, `change` = close / entry - 1
    # (entry, change NaN when not counted).
    stocks: pd.DataFrame
    # Indexed by session ts, from the pick session (0.0) on: equal-weight mean change of the counted
    # instruments; an instrument not bought yet (a gap right after the pick) counts as 0.
    path: pd.Series
    # Instruments in the mean: a close on the pick session and a valid open after it.
    counted: int


def _valid(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s.where(np.isfinite(s) & (s > 0))


def basket_performance(bars: pd.DataFrame, start: pd.Timestamp) -> BasketPerformance:
    """Each instrument's change from the open after `start`'s session, and the equal-weight basket path."""
    empty = BasketPerformance(pd.DataFrame(columns=["entry", "close", "change"]), pd.Series(dtype="float64"), 0)
    day = pd.Timestamp(start).normalize()
    df = bars[["instrument_id", "ts", "open", "close"]].copy()
    df["ts"] = pd.to_datetime(df["ts"])
    df["open"], df["close"] = _valid(df["open"]), _valid(df["close"])
    df = df[df["close"].notna() & (df["ts"].dt.normalize() >= day)]
    df = df.drop_duplicates(["instrument_id", "ts"], keep="last")
    if df.empty:
        return empty

    closes = df.pivot(index="ts", columns="instrument_id", values="close").sort_index()
    opens = df.pivot(index="ts", columns="instrument_id", values="open").reindex_like(closes)
    if closes.index[0].normalize() != day:
        return empty  # nothing traded on the pick session
    listed = closes.columns[closes.iloc[0].notna()]
    closes, opens = closes[listed], opens[listed].iloc[1:]

    entry = opens.bfill().iloc[0] if len(opens) else pd.Series(np.nan, index=listed)
    entry_ts = opens.notna().idxmax().where(opens.notna().any()) if len(opens) else entry
    held = closes.ffill()
    changes = held / entry - 1
    # Zero until each instrument's entry bar (also the pick session itself).
    before = closes.index.values[:, None] < pd.to_datetime(entry_ts).values[None, :]
    changes = changes.mask(before, 0.0)

    counted = entry.index[entry.notna()]
    stocks = pd.DataFrame({"entry": entry, "close": held.iloc[-1], "change": changes.iloc[-1].where(entry.notna())})
    stocks.index.name = "instrument_id"
    path = changes[counted].mean(axis=1) if len(counted) else pd.Series(dtype="float64")
    return BasketPerformance(stocks, path, len(counted))

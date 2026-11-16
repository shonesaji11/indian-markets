"""Cross-sectional scans: a snapshot DataFrame in (one row per instrument, columns from
daily_signals_v1), a ranked DataFrame out. Pure functions, versioned like indicators.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

ScanFunc = Callable[[pd.DataFrame, int], pd.DataFrame]


@dataclass(frozen=True)
class Scan:
    name: str
    version: int
    title: str
    description: str
    metric: str  # the column that explains why a row qualified
    func: ScanFunc

    def run(self, snapshot: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
        if snapshot.empty:
            return snapshot
        return self.func(snapshot, limit)


SCANS: dict[str, Scan] = {}


def scan(name: str, version: int, title: str, description: str, metric: str):
    def wrap(func: ScanFunc) -> ScanFunc:
        SCANS[name] = Scan(name, version, title, description, metric, func)
        return func

    return wrap


def _priced(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["pct_change"].notna()]


@scan("top_gainers", 1, "Top gainers", "Largest % rise vs previous close", "pct_change")
def top_gainers(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    df = _priced(df)
    return df[df["pct_change"] > 0].nlargest(limit, "pct_change")


@scan("top_losers", 1, "Top losers", "Largest % fall vs previous close", "pct_change")
def top_losers(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    df = _priced(df)
    return df[df["pct_change"] < 0].nsmallest(limit, "pct_change")


@scan("volume_shockers", 1, "Volume shockers", "Volume at least 2× the prior 20-day average",
      "relative_volume")
def volume_shockers(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    df = df[df["relative_volume"] >= 2]
    return df.nlargest(limit, "relative_volume")


@scan("new_52w_highs", 1, "52-week highs", "Traded at a new 52-week high", "from_high_52w")
def new_52w_highs(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    # Require ~a year of history so recent listings don't count every day as a "high".
    df = df[(df["bars_252"] >= 240) & (df["high"] >= df["high_52w"])]
    return _priced(df).nlargest(limit, "pct_change")


@scan("new_52w_lows", 1, "52-week lows", "Traded at a new 52-week low", "pct_change")
def new_52w_lows(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    df = df[(df["bars_252"] >= 240) & (df["low"] <= df["low_52w"])]
    return _priced(df).nsmallest(limit, "pct_change")


@scan("gap_ups", 1, "Gap ups", "Opened at least 2% above previous close", "gap_pct")
def gap_ups(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    return df[df["gap_pct"] >= 0.02].nlargest(limit, "gap_pct")


@scan("gap_downs", 1, "Gap downs", "Opened at least 2% below previous close", "gap_pct")
def gap_downs(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    return df[df["gap_pct"] <= -0.02].nsmallest(limit, "gap_pct")


def breadth(df: pd.DataFrame) -> dict:
    """Advance/decline counts and share of stocks above their moving averages."""
    if df.empty:
        return {"total": 0, "advances": 0, "declines": 0, "unchanged": 0,
                "above_sma_50": None, "above_sma_200": None, "new_highs": 0, "new_lows": 0}
    chg = df["pct_change"].dropna()

    def share_above(col: str):
        valid = df[df[col].notna()]
        return float((valid["close"] > valid[col]).mean()) if len(valid) else None

    seasoned = df["bars_252"] >= 240
    return {
        "total": int(len(chg)),
        "advances": int((chg > 0).sum()),
        "declines": int((chg < 0).sum()),
        "unchanged": int((chg == 0).sum()),
        "above_sma_50": share_above("sma_50"),
        "above_sma_200": share_above("sma_200"),
        "new_highs": int((seasoned & (df["high"] >= df["high_52w"])).sum()),
        "new_lows": int((seasoned & (df["low"] <= df["low_52w"])).sum()),
    }

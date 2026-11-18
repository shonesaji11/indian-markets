"""Data-quality checks over stored daily bars. Pure functions: bars in, issues out.

Bars are long format (instrument_id, ts, open, high, low, close, volume, instrument_type). Every check
returns an issues frame with columns instrument_id, start_ts, end_ts, detail. The service
(pipelines/data_quality.py) decides which bars to check, stores the issues and resolves the ones that
stop appearing. Bump DQ_VERSION whenever a check's logic or threshold changes: the next run then
re-checks all history.
"""

from __future__ import annotations

import pandas as pd

DQ_VERSION = 1
STALE_SESSIONS = 3        # no new bar for more than this many sessions the market traded
JUMP_THRESHOLD = 0.35     # |close / previous close - 1|; most NSE stocks have circuit limits of 20% or less
MIN_HISTORY_BARS = 200    # fewer bars than this is a new listing: recorded as expected, not flagged
SESSION_SHARE = 0.25      # a day is a market session if at least this share of a typical day's instruments traded

ISSUE_COLUMNS = ["instrument_id", "start_ts", "end_ts", "detail"]


def _issues(df: pd.DataFrame) -> pd.DataFrame:
    return df[ISSUE_COLUMNS].reset_index(drop=True) if len(df) else pd.DataFrame(columns=ISSUE_COLUMNS)


def trading_sessions(counts: pd.Series) -> pd.DatetimeIndex:
    """Market sessions from instruments-per-day counts (index ts): days on which a normal share of
    instruments traded. Drops stray days where a handful of instruments have a bar (e.g. a bad tick
    on a holiday), which would otherwise make every other stock look like it has a gap."""
    if counts.empty:
        return pd.DatetimeIndex([])
    keep = counts[counts >= SESSION_SHARE * counts.median()]
    return pd.DatetimeIndex(sorted(keep.index))


def find_gaps(bars: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """Runs of market sessions with no bar, between an instrument's first and last bar in `bars`."""
    df = bars[["instrument_id", "ts"]].drop_duplicates()
    df = df[df["ts"].isin(sessions)].sort_values(["instrument_id", "ts"])
    if df.empty:
        return _issues(df)
    df["pos"] = sessions.searchsorted(df["ts"])
    df["prev_pos"] = df.groupby("instrument_id")["pos"].shift()
    gaps = df[df["pos"] - df["prev_pos"] > 1].copy()
    gaps["start_ts"] = sessions[gaps["prev_pos"].astype(int) + 1]
    gaps["end_ts"] = sessions[gaps["pos"] - 1]
    missing = gaps["pos"] - gaps["prev_pos"].astype(int) - 1
    gaps["detail"] = missing.map(lambda n: f"{n} session{'s' if n != 1 else ''} with no bar")
    return _issues(gaps)


def find_bad_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Bars with a missing or non-positive price, high below low, or no volume (indices excluded:
    their volume is always 0)."""
    df = bars.copy()
    prices = df[["open", "high", "low", "close"]]
    reasons = {
        "missing or zero price": prices.isna().any(axis=1) | (prices <= 0).any(axis=1),
        "high below low": df["high"] < df["low"],
        "no volume": (df["instrument_type"] != "INDEX") & ~(df["volume"] > 0),
    }
    flags = pd.DataFrame(reasons)
    df = df[flags.any(axis=1)]
    if df.empty:
        return _issues(df)
    df["detail"] = flags.loc[df.index].apply(lambda r: ", ".join(k for k, v in r.items() if v), axis=1)
    df["start_ts"] = df["end_ts"] = df["ts"]
    return _issues(df)


def find_jumps(bars: pd.DataFrame, threshold: float = JUMP_THRESHOLD) -> pd.DataFrame:
    """Closes that move more than `threshold` from the previous bar: usually a split or bonus the
    stored history hasn't been adjusted for, sometimes a bad tick."""
    df = bars[bars["instrument_type"] != "INDEX"].sort_values(["instrument_id", "ts"])
    df = df[df["close"] > 0]
    prev = df.groupby("instrument_id")["close"].shift()
    move = df["close"] / prev - 1
    jumps = df[move.abs() > threshold].copy()
    if jumps.empty:
        return _issues(jumps)
    jumps["start_ts"] = jumps["end_ts"] = jumps["ts"]
    jumps["detail"] = move[jumps.index].map(lambda m: f"close {m:+.0%} vs previous bar")
    return _issues(jumps)


def find_stale(last_bar: pd.Series, sessions: pd.DatetimeIndex, max_behind: int = STALE_SESSIONS) -> pd.DataFrame:
    """Instruments (index of `last_bar`, value = their latest bar's ts) more than `max_behind` market
    sessions behind the latest session."""
    if last_bar.empty or len(sessions) == 0:
        return pd.DataFrame(columns=ISSUE_COLUMNS)
    behind = len(sessions) - sessions.searchsorted(pd.to_datetime(last_bar.values), side="right")
    df = pd.DataFrame({"instrument_id": last_bar.index, "start_ts": last_bar.values, "behind": behind})
    df = df[df["behind"] > max_behind]
    df["end_ts"] = sessions[-1]
    df["detail"] = df["behind"].map(lambda n: f"no bar for the last {n} sessions")
    return _issues(df)


def find_short_history(bar_counts: pd.Series, first_bar: pd.Series, min_bars: int = MIN_HISTORY_BARS) -> pd.DataFrame:
    """Instruments with fewer than `min_bars` daily bars (expected for new listings)."""
    short = bar_counts[bar_counts < min_bars]
    df = pd.DataFrame({"instrument_id": short.index, "start_ts": first_bar.reindex(short.index).values,
                       "end_ts": first_bar.reindex(short.index).values})
    df["detail"] = short.map(lambda n: f"{n} bars, fewer than {min_bars}").values
    return _issues(df)


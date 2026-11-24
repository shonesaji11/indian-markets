"""Big-mover features: what is known at the close of session t-1 about each stock, used to score how likely
it is to move >= 4% close-vs-open on session t (the "big movers" watchlist, `pipelines/movers.py`).

Ported from the research study (`research/movers/features.py`, night-before features only; the study's
rules and results are in its README.md / REPORT.md). One implementation for both: the research can import
`build_features` from here. Any change to a feature's logic changes what the stored model was trained on:
bump `FEATURES_VERSION` and train a new model version (loading a model with another version fails).

Inputs are long-format daily bars. ATR = 14-day Wilder ATR, as on the dashboard. Market features use the
Nifty 50 (sessions calendar, returns, trend) and India VIX, plus the cross-section of the stocks passed in
(share above SMA20, share with a big move), so pass the whole universe, not a filtered list.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

FEATURES_VERSION = 1
BIG_MOVE = 0.04  # |close/open - 1| on day t
MIN_BARS = 60  # prior bars a stock needs to be scored
HISTORY_BARS = 500  # bars per stock that scoring loads: 252-bar windows + ~250 bars for ATR's smoothing to settle

# Model input order. It is part of the trained model (column sampling depends on it): never reorder.
FEATURE_COLUMNS: tuple[str, ...] = (
    "atr_pct", "atr_ratio", "range_atr", "nr7", "inside", "body_atr", "close_pos", "gap_atr", "vol_ratio",
    "vol3_ratio", "turnover_cr", "dist_sma10_atr", "dist_sma20_atr", "dist_sma50_atr", "stack",
    "sma20_slope_atr", "ret1_atr", "ret5_atr", "ret20_atr", "pos20", "pos52", "piv_p_atr", "piv_r1_atr",
    "piv_s1_atr", "piv_r2_atr", "piv_s2_atr", "piv_r3_atr", "piv_s3_atr", "cpr_width_atr", "beta60", "corr60",
    "atr_pos252", "bbw", "bbw_pos252", "narrow_streak", "vol5_50", "upvol_share20", "max_co20_atr",
    "gap_freq20", "big_rate20", "big_rate60", "to_wk_high_atr", "to_wk_low_atr", "above_wk_high",
    "below_wk_low", "to_mo_high_atr", "to_mo_low_atr", "above_mo_high", "below_mo_low", "to_day_high_atr",
    "to_day_low_atr", "nifty_ret1", "nifty_above_sma20", "nifty_above_sma50", "nifty_atr_ratio", "vix",
    "vix_chg5", "vix_ratio50", "vix_pos252", "breadth_sma20", "mkt_big_share", "rel20", "weekday",
)
_BARS = ["open", "high", "low", "close", "volume"]


def _groll(s: pd.DataFrame, z: pd.Series, n: int, fn: str = "mean", minp: Optional[int] = None) -> pd.Series:
    """Rolling stat of a series z (aligned to s, rows sorted by stock then date) per stock."""
    r = z.groupby(s.instrument_id).rolling(n, min_periods=minp or n)
    return getattr(r, fn)().reset_index(level=0, drop=True)


def _roll(s: pd.DataFrame, col: str, n: int, fn: str = "mean", minp: Optional[int] = None) -> pd.Series:
    return _groll(s, s[col], n, fn, minp)


def _pos_in_range(s: pd.DataFrame, z: pd.Series, n: int = 252, minp: int = 200) -> pd.Series:
    """Where z sits between its own min (0) and max (1) over the last n bars."""
    lo, hi = _groll(s, z, n, "min", minp), _groll(s, z, n, "max", minp)
    return (z - lo) / (hi - lo)


def wilder_atr(s: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder ATR per stock (same as the `atr` indicator)."""
    pc = s.groupby("instrument_id")["close"].shift()
    tr = pd.concat([s.high - s.low, (s.high - pc).abs(), (s.low - pc).abs()], axis=1).max(axis=1)
    return tr.groupby(s.instrument_id).transform(lambda x: x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean())


def _eod_features(s: pd.DataFrame) -> pd.DataFrame:
    """Features as of each row's own close (the caller shifts them to the next session)."""
    c, h, l, o, v = s.close, s.high, s.low, s.open, s.volume
    g = s.groupby("instrument_id")
    a = wilder_atr(s)
    sma = {n: _roll(s, "close", n) for n in (10, 20, 50)}
    rng = h - l
    f = pd.DataFrame(index=s.index)
    f["atr_pct"] = a / c
    f["atr_ratio"] = a / a.groupby(s.instrument_id).transform(lambda x: x.rolling(50).mean())
    f["range_atr"] = rng / a
    f["nr7"] = (rng <= rng.groupby(s.instrument_id).transform(lambda x: x.rolling(7).min())).astype(float)
    f["inside"] = ((h <= g.high.shift()) & (l >= g.low.shift())).astype(float)
    f["body_atr"] = (c - o) / a
    f["close_pos"] = np.where(rng > 0, (c - l) / rng.where(rng > 0), 0.5)
    f["gap_atr"] = (o - g.close.shift()) / a
    v20 = v.groupby(s.instrument_id).transform(lambda x: x.rolling(20).mean().shift())
    f["vol_ratio"] = v / v20
    f["vol3_ratio"] = _roll(s, "volume", 3) / v20
    f["turnover_cr"] = (c * v).groupby(s.instrument_id).transform(lambda x: x.rolling(20).median()) / 1e7
    for n in (10, 20, 50):
        f[f"dist_sma{n}_atr"] = (c - sma[n]) / a
    f["stack"] = ((c > sma[10]) & (sma[10] > sma[20]) & (sma[20] > sma[50])).astype(float)
    f["sma20_slope_atr"] = (sma[20] - sma[20].groupby(s.instrument_id).shift(5)) / a
    for n in (1, 5, 20):
        f[f"ret{n}_atr"] = (c - g.close.shift(n)) / a
    f["ret20"] = c / g.close.shift(20) - 1
    hi20, lo20 = _roll(s, "high", 20, "max"), _roll(s, "low", 20, "min")
    hi52, lo52 = _roll(s, "high", 252, "max", 200), _roll(s, "low", 252, "min", 200)
    f["pos20"] = (c - lo20) / (hi20 - lo20)
    f["pos52"] = (c - lo52) / (hi52 - lo52)
    # classic pivots for the next session from this session's H/L/C, as distance from this close in ATRs
    p = (h + l + c) / 3
    lv = {"p": p, "r1": 2 * p - l, "s1": 2 * p - h, "r2": p + rng, "s2": p - rng,
          "r3": h + 2 * (p - l), "s3": l - 2 * (h - p)}
    for k, x in lv.items():
        f[f"piv_{k}_atr"] = (x - c) / a
    f["cpr_width_atr"] = (2 * p - (h + l)).abs() / a  # |TC - BC| with BC = (H+L)/2, TC = 2P - BC
    # beta / correlation to the Nifty over 60 sessions (daily close-to-close returns)
    r, x = c / g.close.shift() - 1, s.mret
    mx, my = _groll(s, x, 60, minp=40), _groll(s, r, 60, minp=40)
    cov = _groll(s, x * r, 60, minp=40) - mx * my
    vx, vy = _groll(s, x * x, 60, minp=40) - mx ** 2, _groll(s, r * r, 60, minp=40) - my ** 2
    f["beta60"] = cov / vx
    f["corr60"] = cov / np.sqrt(vx * vy)
    # contraction: volatility against its own last year; narrow-day streak
    f["atr_pos252"] = _pos_in_range(s, a / c)
    bbw = 4 * _roll(s, "close", 20, "std") / sma[20]
    f["bbw"], f["bbw_pos252"] = bbw, _pos_in_range(s, bbw)
    narrow = (rng < a).astype(int)
    f["narrow_streak"] = narrow.groupby([s.instrument_id, (narrow == 0).groupby(s.instrument_id).cumsum()]).cumsum()
    # volume and shock history
    f["vol5_50"] = _roll(s, "volume", 5) / _roll(s, "volume", 50)
    f["upvol_share20"] = _groll(s, v.where(c > g.close.shift(), 0), 20, "sum") / _roll(s, "volume", 20, "sum")
    f["max_co20_atr"] = _groll(s, (c / o - 1).abs(), 20, "max") / (a / c)
    f["gap_freq20"] = _groll(s, ((o - g.close.shift()).abs() > a).astype(float), 20)
    f["sma20_up"] = (c > sma[20]).astype(float)
    f["atr"] = a
    f["bars"] = g.cumcount() + 1
    return f


def _period_levels(s: pd.DataFrame, freq: str) -> pd.DataFrame:
    """High/low of the last completed calendar week/month before each row's period."""
    per = s.ts.dt.to_period(freq)
    agg = s.assign(per=per).groupby(["instrument_id", "per"]).agg(ph=("high", "max"), pl=("low", "min"))
    agg = agg.groupby(level=0).shift(1).reset_index()
    return s[["instrument_id"]].assign(per=per).merge(agg, on=["instrument_id", "per"], how="left")[["ph", "pl"]]


def _clean(bars: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Date-only ts, one bar per (instrument, day) (the last one wins), sorted by stock then date."""
    d = bars[cols].copy()
    d["ts"] = pd.to_datetime(d["ts"]).dt.normalize()
    values = cols[2:]
    d[values] = d[values].astype(float)
    return d.drop_duplicates(["instrument_id", "ts"], keep="last").sort_values(["instrument_id", "ts"]).reset_index(drop=True)


def next_weekday(ts: pd.Timestamp) -> pd.Timestamp:
    """The next Monday-Friday after `ts`: the assumed next session (there is no holiday calendar)."""
    ts = pd.Timestamp(ts).normalize()
    return ts + pd.offsets.BDay(1)


def build_features(stocks: pd.DataFrame, nifty: pd.DataFrame, vix: pd.DataFrame,
                   target: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """One row per stock and session t with the features known at the t-1 close.

    stocks: long daily bars (instrument_id, ts, open, high, low, close, volume) of the whole universe.
    nifty, vix: daily bars (ts, open, high, low, close) of the Nifty 50 and India VIX.
    target=None (training): every session t in the bars, with the target `move` (close/open - 1 on t) and
      `big` (|move| >= BIG_MOVE); rows whose target is unknown are dropped.
    target=a date after the last bar (scoring): only that session, for every stock (move/big are NaN).

    A row is kept only if the stock traded on the market's previous session (the Nifty's) and has
    MIN_BARS+ prior bars. Columns: instrument_id, ts, FEATURE_COLUMNS, move, big, atr, bars, prev_close.
    """
    s = _clean(stocks, ["instrument_id", "ts", *_BARS])
    n = _clean(nifty.assign(instrument_id=0, volume=0.0), ["instrument_id", "ts", *_BARS])
    vx = _clean(vix.assign(instrument_id=0, volume=0.0), ["instrument_id", "ts", "close"])
    vx = vx[["ts", "close"]].rename(columns={"close": "vix"})
    if target is not None:
        target = pd.Timestamp(target).normalize()
        if (not s.empty and target <= s.ts.max()) or (not n.empty and target <= n.ts.max()):
            raise ValueError(f"target {target.date()} must be after the last bar")
        # an empty bar for day t, so that "shift to the next row" puts the t-1 features there
        blank = pd.DataFrame({"instrument_id": s.instrument_id.unique(), "ts": target})
        s = pd.concat([s, blank]).sort_values(["instrument_id", "ts"]).reset_index(drop=True)
        n = pd.concat([n, pd.DataFrame({"instrument_id": [0], "ts": [target]})]).reset_index(drop=True)

    s["_nc"] = s.ts.map(dict(zip(n.ts, n.close)))
    s["mret"] = s._nc / s.ts.map(dict(zip(n.ts, n.close.shift()))) - 1  # the Nifty's return that session
    sessions = pd.Series(n.ts.values)
    prev_session = dict(zip(sessions.iloc[1:].values, sessions.iloc[:-1].values))

    f = _eod_features(s)
    m = s.close / s.open - 1
    big = (m.abs() >= BIG_MOVE).astype(float).where(m.notna())
    f["big_rate20"] = big.groupby(s.instrument_id).transform(lambda x: x.rolling(20).mean())
    f["big_rate60"] = big.groupby(s.instrument_id).transform(lambda x: x.rolling(60).mean())
    own_day_up20 = f["sma20_up"].copy()

    # shift every feature to the next row of the same stock (known at that row's previous close)
    cols = list(f.columns)
    f[cols] = f.groupby(s.instrument_id)[cols].shift(1)
    out = pd.concat([s[["instrument_id", "ts"]], f], axis=1)
    out["prev_ts"] = s.groupby("instrument_id").ts.shift(1)
    out["prev_close"] = s.groupby("instrument_id").close.shift(1)
    out["move"], out["big"] = m, big

    for freq, tag in (("W", "wk"), ("M", "mo")):
        lv = _period_levels(s, freq)
        out[f"to_{tag}_high_atr"] = (lv.ph - out.prev_close) / out.atr
        out[f"to_{tag}_low_atr"] = (out.prev_close - lv.pl) / out.atr
        out[f"above_{tag}_high"] = (out.prev_close > lv.ph).astype(float).where(lv.ph.notna())
        out[f"below_{tag}_low"] = (out.prev_close < lv.pl).astype(float).where(lv.pl.notna())
    out["to_day_high_atr"] = (s.groupby("instrument_id").high.shift(1) - out.prev_close) / out.atr
    out["to_day_low_atr"] = (out.prev_close - s.groupby("instrument_id").low.shift(1)) / out.atr

    # market features, as of the previous session
    nf = pd.DataFrame({"ts": n.ts})
    nc = n.close
    nf["nifty_ret1"] = nc / nc.shift() - 1
    nf["nifty_ret20"] = nc / nc.shift(20) - 1
    nf["nifty_above_sma20"] = (nc > nc.rolling(20).mean()).astype(float)
    nf["nifty_above_sma50"] = (nc > nc.rolling(50).mean()).astype(float)
    na = wilder_atr(n)
    nf["nifty_atr_ratio"] = na / na.rolling(50).mean()
    nf = nf.merge(vx, on="ts", how="left")
    v_ = nf.vix
    nf["vix_chg5"] = v_ / v_.shift(5) - 1
    nf["vix_ratio50"] = v_ / v_.rolling(50, min_periods=40).mean()  # VIX lacks a few sessions (2021)
    lo, hi = v_.rolling(252, min_periods=200).min(), v_.rolling(252, min_periods=200).max()
    nf["vix_pos252"] = (v_ - lo) / (hi - lo)
    day = pd.DataFrame({"ts": s.ts, "up20": own_day_up20.where(s.close.notna()), "big": big})
    breadth = day.groupby("ts").agg(breadth_sma20=("up20", "mean"), mkt_big_share=("big", "mean")).reset_index()
    nf = nf.merge(breadth, on="ts", how="left")
    mcols = [c for c in nf.columns if c != "ts"]
    nf[mcols] = nf[mcols].shift(1)
    out = out.merge(nf, on="ts", how="left")
    out["rel20"] = out.ret20 - out.nifty_ret20
    out["weekday"] = out.ts.dt.weekday

    out["prev_session"] = out.ts.map(prev_session)
    ok = (out.prev_ts == out.prev_session) & (out.bars >= MIN_BARS)
    ok &= out.big.notna() if target is None else out.ts == target
    out = out[ok]
    return out[["instrument_id", "ts", *FEATURE_COLUMNS, "move", "big", "atr", "bars", "prev_close"]].reset_index(drop=True)

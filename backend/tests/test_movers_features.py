"""Big-movers features (engine/movers.py): hand-computed reference values and data edge cases."""

import numpy as np
import pandas as pd
import pytest

from markets.engine.movers import FEATURE_COLUMNS, build_features, next_weekday

DAYS = pd.bdate_range("2024-01-01", periods=80)  # Mon 1 Jan .. Fri 19 Apr 2024
LAST = DAYS[-1]
NEXT = next_weekday(LAST)  # Mon 22 Apr


def flat(iid, days=DAYS, price=100.0, rng=2.0, volume=1000.0):
    """Open = close = price, high/low = price ± rng/2: true range is `rng` every day."""
    return pd.DataFrame({"instrument_id": iid, "ts": days, "open": price, "high": price + rng / 2,
                         "low": price - rng / 2, "close": price, "volume": volume})


def index(days=DAYS, close=None):
    close = np.full(len(days), 20000.0) if close is None else np.asarray(close, dtype=float)
    return pd.DataFrame({"ts": days, "open": close, "high": close + 50, "low": close - 50, "close": close})


def score(stocks, nifty=None, vix=None, target=NEXT):
    return build_features(stocks, index() if nifty is None else nifty, index(close=np.full(80, 15.0)) if vix is None else vix,
                          target).set_index("instrument_id")


def test_flat_prices_reference_values():
    row = score(flat(2)).loc[2]
    expected = {
        "atr_pct": 0.02, "range_atr": 1.0, "close_pos": 0.5, "body_atr": 0.0, "gap_atr": 0.0, "nr7": 1.0,
        "inside": 1.0, "piv_p_atr": 0.0, "piv_r1_atr": 0.5, "piv_s1_atr": -0.5, "piv_r2_atr": 1.0,
        "piv_s2_atr": -1.0, "piv_r3_atr": 1.5, "piv_s3_atr": -1.5, "cpr_width_atr": 0.0, "dist_sma20_atr": 0.0,
        "stack": 0.0, "ret1_atr": 0.0, "pos20": 0.5, "vol_ratio": 1.0, "vol3_ratio": 1.0, "vol5_50": 1.0,
        "turnover_cr": 0.01, "upvol_share20": 0.0, "max_co20_atr": 0.0, "gap_freq20": 0.0, "big_rate20": 0.0,
        "narrow_streak": 0.0, "to_day_high_atr": 0.5, "to_day_low_atr": 0.5, "weekday": 0,
    }
    for k, v in expected.items():
        assert row[k] == pytest.approx(v, abs=1e-12), k
    assert np.isnan(row["pos52"]) and np.isnan(row["beta60"])  # 80 bars: < 200 for 52 weeks, flat Nifty for beta
    assert row["move"] != row["move"]  # NaN: day t hasn't happened


def test_one_wide_day_reference_values():
    s = flat(2)
    s.loc[s.ts == LAST, ["open", "high", "low", "close"]] = [100.0, 110.0, 95.0, 108.0]
    row = score(s).loc[2]
    atr = 2 + (15 - 2) / 14  # Wilder: true range 15 after a steady 2
    p = (110 + 95 + 108) / 3
    assert row["atr_pct"] == pytest.approx(atr / 108)
    assert row["range_atr"] == pytest.approx(15 / atr)
    assert row["body_atr"] == pytest.approx(8 / atr)
    assert row["close_pos"] == pytest.approx(13 / 15)
    assert row["ret1_atr"] == pytest.approx(8 / atr)
    assert row["piv_r1_atr"] == pytest.approx((2 * p - 95 - 108) / atr)
    assert row["piv_r3_atr"] == pytest.approx((110 + 2 * (p - 95) - 108) / atr)
    assert row["piv_s3_atr"] == pytest.approx((95 - 2 * (110 - p) - 108) / atr)
    assert row["cpr_width_atr"] == pytest.approx(abs(2 * p - 205) / atr)
    assert row["to_day_high_atr"] == pytest.approx(2 / atr)
    assert (row["inside"], row["nr7"]) == (0.0, 0.0)
    assert row["max_co20_atr"] == pytest.approx(0.08 / (atr / 108))  # |108/100 - 1| in units of ATR%
    assert row["big_rate20"] == pytest.approx(1 / 20)  # one 8% close-vs-open day in the last 20


def test_week_and_month_levels():
    s = flat(2)
    s.loc[s.ts == pd.Timestamp("2024-04-10"), "high"] = 120.0  # Wed of the week before LAST's week
    s.loc[s.ts == pd.Timestamp("2024-04-16"), "low"] = 90.0  # Tue of LAST's week (15-19 Apr)
    s.loc[s.ts == pd.Timestamp("2024-03-28"), "high"] = 130.0  # March
    # Monday target: last completed week = LAST's own week (low 90); last month = March (high 130)
    mon = score(s).loc[2]
    atr = mon["atr_pct"] * 100
    assert mon["to_wk_low_atr"] == pytest.approx(10 / atr)
    assert mon["to_wk_high_atr"] == pytest.approx(1 / atr)
    assert mon["to_mo_high_atr"] == pytest.approx(30 / atr)
    assert (mon["above_wk_high"], mon["below_wk_low"]) == (0.0, 0.0)
    # Target inside LAST's week (data ends Thu 18 Apr, target Fri 19 Apr): the completed week is 8-12 Apr
    fri = build_features(s[s.ts < LAST], index()[lambda d: d.ts < LAST], index(close=np.full(80, 15.0)), LAST)
    fri = fri.set_index("instrument_id").loc[2]
    assert fri["to_wk_high_atr"] == pytest.approx(20 / (fri["atr_pct"] * 100))
    assert fri["weekday"] == 4


def test_market_features():
    up = flat(2)
    up.loc[up.ts == LAST, ["open", "high", "close"]] = [100.0, 106.0, 105.0]  # +5%: a big move, above SMA20
    nifty = index(close=np.r_[np.full(79, 20000.0), 20200.0])
    vix = index(close=np.r_[np.full(75, 15.0), 10, 10, 10, 10, 18.0])
    rows = score(pd.concat([up, flat(3), flat(4), flat(5)]), nifty, vix)
    assert rows["nifty_ret1"].unique() == pytest.approx([0.01])
    assert rows["vix"].unique() == pytest.approx([18.0])
    assert rows["vix_chg5"].unique() == pytest.approx([18 / 15 - 1])
    assert rows["mkt_big_share"].unique() == pytest.approx([0.25])
    assert rows["breadth_sma20"].unique() == pytest.approx([0.25])  # flat stocks sit on their SMA, not above
    assert rows["nifty_above_sma20"].unique() == pytest.approx([1.0])
    assert rows.loc[2, "rel20"] == pytest.approx(0.05 - 0.01)


def test_missing_vix_bar_leaves_vix_features_empty():
    vix = index(close=np.full(80, 15.0))
    row = score(flat(2), vix=vix[vix.ts != LAST]).loc[2]
    assert np.isnan(row["vix"]) and np.isnan(row["vix_chg5"])
    assert row["atr_pct"] == pytest.approx(0.02)


def test_eligibility_short_history_and_suspension():
    short = flat(3, days=DAYS[-60:])  # 60 bars: the 60th is t-1, so bars = 60 counts
    shorter = flat(4, days=DAYS[-59:])
    suspended = flat(5, days=DAYS[:-1])  # no bar on the last session
    rows = score(pd.concat([flat(2), short, shorter, suspended]))
    assert sorted(rows.index) == [2, 3]


def test_training_rows_skip_days_after_a_gap():
    gap = flat(2)
    gap = gap[gap.ts != DAYS[70]]  # missing session: the next day's features would be stale
    rows = build_features(gap, index(), index(close=np.full(80, 15.0)))
    assert DAYS[71] not in set(rows.ts) and DAYS[72] in set(rows.ts)
    assert rows.ts.min() == DAYS[60]  # first day with 60 prior bars
    assert rows["big"].notna().all() and set(rows["big"]) <= {0.0, 1.0}


def test_unsorted_and_duplicate_bars_give_the_same_rows():
    s = pd.concat([flat(2), flat(3, price=50.0)])
    s.loc[s.index[-5], "close"] = 52.0
    clean = score(s)
    messy = pd.concat([s, s.iloc[:30]]).sample(frac=1, random_state=1)  # shuffled, 30 bars twice
    pd.testing.assert_frame_equal(score(messy), clean)


def test_zero_and_nan_values_do_not_break_scoring():
    s = flat(2, volume=0.0)  # no volume at all
    nan_day = flat(3)
    nan_day.loc[nan_day.ts == DAYS[-3], ["close", "volume"]] = np.nan
    rows = score(pd.concat([s, nan_day, flat(4)]))
    assert sorted(rows.index) == [2, 3, 4]
    assert np.isnan(rows.loc[2, "vol_ratio"]) and np.isnan(rows.loc[2, "vol5_50"])  # 0 / 0
    assert rows.loc[4, "atr_pct"] == pytest.approx(0.02)


def test_scoring_row_equals_the_training_row_for_the_same_day():
    rng = np.random.default_rng(0)

    def walk(iid, days):
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, len(days))))
        o = c * (1 + rng.normal(0, 0.015, len(days)))
        return pd.DataFrame({"instrument_id": iid, "ts": days, "open": o, "high": np.maximum(o, c) * 1.01,
                             "low": np.minimum(o, c) * 0.99, "close": c, "volume": rng.integers(1, 9, len(days)) * 1e3})

    days = pd.bdate_range("2023-01-02", periods=301)
    stocks = pd.concat([walk(i, days) for i in range(2, 9)])
    nifty, vix = walk(0, days).drop(columns="instrument_id"), walk(0, days).drop(columns="instrument_id")
    t = days[-1]
    trained = build_features(stocks, nifty, vix)
    trained = trained[trained.ts == t].set_index("instrument_id")[list(FEATURE_COLUMNS)]
    scored = build_features(stocks[stocks.ts < t], nifty[nifty.ts < t], vix[vix.ts < t], t)
    pd.testing.assert_frame_equal(scored.set_index("instrument_id")[list(FEATURE_COLUMNS)], trained)


def test_target_must_follow_the_bars():
    with pytest.raises(ValueError):
        build_features(flat(2), index(), index(), LAST)


def test_next_weekday():
    assert next_weekday(pd.Timestamp("2024-04-19")) == pd.Timestamp("2024-04-22")  # Fri -> Mon
    assert next_weekday(pd.Timestamp("2024-04-16 15:30")) == pd.Timestamp("2024-04-17")

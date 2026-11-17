import math

import numpy as np
import pandas as pd
import pytest

from markets.engine.performance import basket_performance

D0 = pd.Timestamp("2026-11-13")
D1, D2, D3 = pd.Timestamp("2026-11-14"), pd.Timestamp("2026-11-17"), pd.Timestamp("2026-11-18")


def bars(*rows):
    """Rows of (instrument_id, ts, open, close)."""
    return pd.DataFrame(rows, columns=["instrument_id", "ts", "open", "close"])


def test_reference_values_buy_at_next_open():
    perf = basket_performance(
        bars((1, D1, 98, 100), (1, D2, 105, 110), (1, D3, 110, 121),
             (2, D1, 52, 50), (2, D2, 48, 45), (2, D3, 45, 45)), D1)
    a2, a3, b = 110 / 105 - 1, 121 / 105 - 1, 45 / 48 - 1
    assert perf.counted == 2
    assert perf.path.index.tolist() == [D1, D2, D3]
    assert perf.path.tolist() == pytest.approx([0.0, (a2 + b) / 2, (a3 + b) / 2])
    assert perf.stocks.loc[1, "entry"] == 105 and perf.stocks.loc[1, "close"] == 121
    assert perf.stocks.loc[1, "change"] == pytest.approx(a3)


def test_gap_after_entry_carries_last_close():
    perf = basket_performance(bars((1, D1, 1, 100), (1, D2, 100, 110), (1, D3, 110, 120),
                                   (2, D1, 1, 50), (2, D2, 50, 50)), D1)
    assert perf.path.tolist() == pytest.approx([0.0, 0.05, 0.1])


def test_gap_right_after_pick_counts_as_zero_until_bought():
    perf = basket_performance(bars((1, D1, 1, 100), (1, D2, 100, 110), (1, D3, 110, 120),
                                   (2, D1, 1, 50), (2, D3, 50, 55)), D1)
    assert perf.stocks.loc[2, "entry"] == 50
    assert perf.path.tolist() == pytest.approx([0.0, 0.05, 0.15])


def test_no_bar_after_pick_is_listed_but_not_counted():
    perf = basket_performance(bars((1, D1, 1, 100), (1, D2, 100, 110), (3, D1, 1, 70)), D1)
    assert perf.counted == 1
    assert math.isnan(perf.stocks.loc[3, "change"]) and perf.stocks.loc[3, "close"] == 70
    assert perf.path.tolist() == pytest.approx([0.0, 0.1])


def test_no_close_on_pick_session_is_left_out():
    perf = basket_performance(bars((1, D1, 1, 100), (1, D2, 100, 110), (4, D2, 30, 31), (4, D3, 31, 33)), D1)
    assert perf.stocks.index.tolist() == [1]


def test_bad_open_and_close_values():
    # Zero open on the first bar after the pick: bought at the next valid open instead.
    perf = basket_performance(bars((1, D1, 1, 100), (1, D2, 0, 104), (1, D3, 105, 110)), D1)
    assert perf.stocks.loc[1, "entry"] == 105
    assert perf.path.tolist() == pytest.approx([0.0, 0.0, 110 / 105 - 1])
    # Zero / NaN close is a gap: the last close is held.
    perf = basket_performance(bars((1, D1, 1, 100), (1, D2, 100, 110), (1, D3, 111, 0),
                                   (2, D1, 1, 10), (2, D2, 10, 12), (2, D3, 12, np.nan)), D1)
    assert perf.path.index.tolist() == [D1, D2]  # no usable close on D3 at all
    # A zero close on the pick session means it isn't listed.
    assert basket_performance(bars((1, D1, 1, 0), (1, D2, 100, 110)), D1).stocks.empty


def test_unsorted_and_duplicate_rows():
    rows = bars((2, D3, 45, 45), (1, D2, 105, 110), (1, D1, 98, 100), (2, D1, 52, 50),
                (1, D3, 999, 999), (1, D3, 110, 121), (2, D2, 48, 45))
    perf = basket_performance(rows, D1)  # the later duplicate wins
    assert perf.path.iloc[-1] == pytest.approx((121 / 105 - 1 + 45 / 48 - 1) / 2)


def test_flat_prices_and_bars_before_start():
    perf = basket_performance(bars((1, D0, 80, 80), (1, D1, 100, 100), (1, D2, 100, 100)), D1)
    assert perf.path.tolist() == [0.0, 0.0]


def test_empty_and_missing_pick_session():
    assert basket_performance(bars(), D1).path.empty
    perf = basket_performance(bars((1, D2, 100, 110), (1, D3, 110, 120)), D1)  # nothing on the pick day
    assert perf.path.empty and perf.counted == 0 and perf.stocks.empty
    only_pick = basket_performance(bars((1, D1, 100, 100)), D1)  # picked today: nothing bought yet
    assert only_pick.counted == 0 and only_pick.path.empty


def test_start_time_of_day_is_ignored():
    perf = basket_performance(bars((1, D1, 1, 100), (1, D2, 100, 110)), D1 + pd.Timedelta(hours=23, minutes=59))
    assert perf.path.tolist() == pytest.approx([0.0, 0.1])

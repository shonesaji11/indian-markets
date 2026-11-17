import math

import numpy as np
import pandas as pd
import pytest

from markets.engine.performance import basket_performance

D1, D2, D3 = pd.Timestamp("2026-11-14"), pd.Timestamp("2026-11-17"), pd.Timestamp("2026-11-18")


def closes(*rows):
    return pd.DataFrame(rows, columns=["instrument_id", "ts", "close"])


def test_reference_values():
    perf = basket_performance(
        closes((1, D1, 100), (1, D2, 110), (1, D3, 121), (2, D1, 50), (2, D2, 45), (2, D3, 45)), D1)
    assert perf.counted == 2
    assert perf.path.index.tolist() == [D1, D2, D3]
    assert perf.path.tolist() == pytest.approx([0.0, 0.0, 0.055])
    assert perf.stocks.loc[1, "close"] == 121 and perf.stocks.loc[1, "change"] == pytest.approx(0.21)
    assert perf.stocks.loc[2, "change"] == pytest.approx(-0.1)


def test_gap_carries_last_close():
    perf = basket_performance(closes((1, D1, 100), (1, D2, 110), (1, D3, 120), (2, D1, 50), (2, D3, 55)), D1)
    assert perf.path.tolist() == pytest.approx([0.0, 0.05, 0.15])


def test_no_bar_after_start_is_listed_but_not_counted():
    perf = basket_performance(closes((1, D1, 100), (1, D2, 110), (3, D1, 70)), D1)
    assert perf.counted == 1
    assert math.isnan(perf.stocks.loc[3, "change"]) and perf.stocks.loc[3, "close"] == 70
    assert perf.path.tolist() == pytest.approx([0.0, 0.1])


def test_no_close_on_start_session_is_left_out():
    perf = basket_performance(closes((1, D1, 100), (1, D2, 110), (4, D2, 30), (4, D3, 33)), D1)
    assert perf.stocks.index.tolist() == [1]
    assert perf.path.tolist() == pytest.approx([0.0, 0.1, 0.1])


def test_zero_and_nan_closes_are_gaps():
    perf = basket_performance(closes((1, D1, 100), (1, D2, 0), (1, D3, 105), (2, D1, 10), (2, D2, np.nan), (2, D3, 11)), D1)
    # No usable close on D2 at all, so D2 isn't a session here.
    assert perf.path.index.tolist() == [D1, D3]
    assert perf.path.tolist() == pytest.approx([0.0, 0.075])
    perf = basket_performance(closes((1, D1, 100), (1, D2, 0), (1, D3, 105), (2, D1, 10), (2, D2, 12), (2, D3, 11)), D1)
    assert perf.path.tolist() == pytest.approx([0.0, 0.1, 0.075])  # stock 1 held flat through its bad bar
    # A zero close on the start session means no entry price.
    assert basket_performance(closes((1, D1, 0), (1, D2, 110)), D1).counted == 0


def test_unsorted_and_duplicate_rows():
    rows = closes((2, D3, 45), (1, D2, 110), (1, D1, 100), (2, D1, 50), (1, D3, 999), (1, D3, 121), (2, D2, 45))
    perf = basket_performance(rows, D1)  # the later duplicate wins
    assert perf.path.tolist() == pytest.approx([0.0, 0.0, 0.055])


def test_flat_prices_and_bars_before_start():
    perf = basket_performance(closes((1, pd.Timestamp("2026-11-13"), 80), (1, D1, 100), (1, D2, 100)), D1)
    assert perf.path.tolist() == [0.0, 0.0]


def test_empty_and_missing_start_session():
    assert basket_performance(closes(), D1).path.empty
    perf = basket_performance(closes((1, D2, 110), (1, D3, 120)), D1)  # start was a holiday for these bars
    assert perf.path.empty and perf.counted == 0 and perf.stocks.empty


def test_start_time_of_day_is_ignored():
    perf = basket_performance(closes((1, D1, 100), (1, D2, 110)), D1 + pd.Timedelta(hours=23, minutes=59))
    assert perf.path.tolist() == pytest.approx([0.0, 0.1])

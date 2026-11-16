import numpy as np
import pandas as pd
import pytest

from markets.engine import IndicatorRegistry, default_registry, indicator


def make_candles(closes):
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B", name="ts")
    close = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000.0})


def test_sma_matches_hand_calculation():
    candles = make_candles([1, 2, 3, 4, 5])
    out = default_registry().get("sma").compute(candles, {"period": 3})
    assert np.isnan(out["sma"].iloc[1])
    assert out["sma"].iloc[2:].tolist() == [2.0, 3.0, 4.0]


def test_rsi_is_100_for_only_gains():
    out = default_registry().get("rsi").compute(make_candles(range(1, 40)), {"period": 14})
    assert out["rsi"].dropna().eq(100).all()


def test_multi_output_indicator_returns_all_columns():
    out = default_registry().get("bollinger").compute(make_candles(np.linspace(100, 120, 50)))
    assert list(out.columns) == ["upper", "middle", "lower"]
    assert (out["upper"].dropna() >= out["lower"].dropna()).all()


def test_calc_id_depends_on_version_and_params():
    spec = default_registry().get("ema")
    assert spec.calc_id(spec.resolve_params({"period": 20})) != spec.calc_id(spec.resolve_params({"period": 50}))
    assert spec.calc_id(spec.resolve_params({})) == spec.calc_id(spec.resolve_params({"period": "20"}))


def test_unknown_params_are_rejected():
    with pytest.raises(ValueError):
        default_registry().get("sma").resolve_params({"length": 5})


def test_custom_registry_is_isolated():
    reg = IndicatorRegistry()

    @indicator("double", version=1, outputs=["x2"], registry=reg)
    def double(candles, factor: float = 2.0):
        return candles["close"] * factor

    out = reg.get("double").compute(make_candles([1, 2]))
    assert out["x2"].tolist() == [2.0, 4.0]

import pandas as pd

from markets.engine.registry import indicator


@indicator("atr", version=1, outputs=["atr"], description="Average True Range (Wilder smoothing)")
def atr(candles: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = candles["close"].shift()
    true_range = pd.concat(
        [candles["high"] - candles["low"], (candles["high"] - prev_close).abs(), (candles["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


@indicator("bollinger", version=1, outputs=["upper", "middle", "lower"], description="Bollinger Bands")
def bollinger(candles: pd.DataFrame, period: int = 20, stddev: float = 2.0) -> pd.DataFrame:
    close = candles["close"]
    middle = close.rolling(period, min_periods=period).mean()
    spread = close.rolling(period, min_periods=period).std(ddof=0) * stddev
    return pd.DataFrame({"upper": middle + spread, "middle": middle, "lower": middle - spread})

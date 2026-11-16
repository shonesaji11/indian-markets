import pandas as pd

from markets.engine.registry import indicator


@indicator("rsi", version=1, outputs=["rsi"], description="Relative Strength Index (Wilder smoothing)")
def rsi(candles: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = candles["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)

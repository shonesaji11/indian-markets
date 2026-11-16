import pandas as pd

from markets.engine.registry import indicator


@indicator("sma", version=1, outputs=["sma"], description="Simple moving average of a price column")
def sma(candles: pd.DataFrame, period: int = 20, source: str = "close") -> pd.Series:
    return candles[source].rolling(period, min_periods=period).mean()


@indicator("ema", version=1, outputs=["ema"], description="Exponential moving average of a price column")
def ema(candles: pd.DataFrame, period: int = 20, source: str = "close") -> pd.Series:
    return candles[source].ewm(span=period, adjust=False, min_periods=period).mean()


@indicator("macd", version=1, outputs=["macd", "signal", "histogram"], description="MACD line, signal and histogram")
def macd(candles: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    close = candles["close"]
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    line.iloc[: slow - 1] = float("nan")
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "histogram": line - sig})

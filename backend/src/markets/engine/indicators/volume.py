import pandas as pd

from markets.engine.registry import indicator

# Both average the bars *before* the current one, so a volume spike is compared with the days
# leading up to it (same convention as avg_volume_20d in daily_signals_v1).


@indicator("volume_avg", version=1, outputs=["volume_avg"], description="Average volume of the previous N bars")
def volume_avg(candles: pd.DataFrame, period: int = 20) -> pd.Series:
    return candles["volume"].shift(1).rolling(period, min_periods=period).mean()


@indicator("relative_volume", version=1, outputs=["relative_volume"],
           description="Volume ÷ average volume of the previous N bars")
def relative_volume(candles: pd.DataFrame, period: int = 20) -> pd.Series:
    avg = candles["volume"].shift(1).rolling(period, min_periods=period).mean()
    return candles["volume"] / avg.where(avg > 0)

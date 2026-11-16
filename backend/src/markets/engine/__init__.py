"""Pure calculations: candle DataFrame in, DataFrame out.

The engine knows nothing about databases, providers or HTTP. It depends only on
pandas/numpy, so it can be unit-tested with hand-built frames and reused in notebooks
or backtests directly.
"""

from markets.engine.registry import IndicatorRegistry, IndicatorSpec, default_registry, indicator

__all__ = ["IndicatorRegistry", "IndicatorSpec", "default_registry", "indicator"]

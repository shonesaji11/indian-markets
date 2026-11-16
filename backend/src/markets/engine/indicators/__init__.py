"""Built-in indicators. Importing this package registers them.

To add one: write a function in a module here, decorate it with @indicator, and import
the module below. If you later change its logic, bump `version`.
"""

from markets.engine.indicators import trend, volatility, momentum, volume  # noqa: F401

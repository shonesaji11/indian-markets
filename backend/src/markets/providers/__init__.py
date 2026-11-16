"""Market data adapters implementing markets.core.ports.MarketDataProvider."""

from __future__ import annotations

from markets.config import Settings
from markets.core.ports import MarketDataProvider


class ProviderError(RuntimeError):
    pass


def build_provider(settings: Settings) -> MarketDataProvider:
    if settings.provider == "fake":
        from markets.providers.fake import FakeProvider

        return FakeProvider()
    if settings.provider == "angelone":
        from markets.providers.angelone import AngelOneProvider

        return AngelOneProvider(
            api_key=settings.angel_api_key,
            client_code=settings.angel_client_code,
            pin=settings.angel_pin,
            totp_secret=settings.angel_totp_secret,
        )
    raise ValueError(f"unknown provider '{settings.provider}'")

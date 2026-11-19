from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Read from environment variables prefixed MARKETS_, or from backend/.env."""

    model_config = SettingsConfigDict(env_prefix="MARKETS_", env_file=BACKEND_DIR / ".env", extra="ignore")

    db_path: Path = BACKEND_DIR / "data" / "markets.duckdb"
    provider: str = "angelone"  # "angelone" or "fake"

    angel_api_key: Optional[str] = None
    angel_client_code: Optional[str] = None
    angel_pin: Optional[str] = None
    angel_totp_secret: Optional[str] = None

    # Alerts by Telegram (notifiers/telegram.py has the setup steps); without both, alerts show in the app only.
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()

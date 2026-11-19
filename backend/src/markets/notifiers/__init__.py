"""Outgoing messages (alerts) implementing markets.core.ports.Notifier."""

from __future__ import annotations

from typing import Optional

from markets.config import Settings
from markets.core.ports import Notifier


class NotifyError(RuntimeError):
    pass


def build_notifier(settings: Settings) -> Optional[Notifier]:
    """Telegram when its bot token and chat id are set in backend/.env, else None (alerts show in the app only)."""
    if settings.telegram_bot_token and settings.telegram_chat_id:
        from markets.notifiers.telegram import TelegramNotifier

        return TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
    return None

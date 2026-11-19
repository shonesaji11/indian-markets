"""Telegram bot messages (Bot API sendMessage).

Setup (by the user): talk to @BotFather to create a bot and get its token, send the bot one message, then read
your chat id from https://api.telegram.org/bot<token>/getUpdates; put both in backend/.env as
MARKETS_TELEGRAM_BOT_TOKEN and MARKETS_TELEGRAM_CHAT_ID.

The token is part of every request URL, and httpx logs request URLs at INFO (on under `markets serve`), so a
filter masks it in httpx's log records.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Callable, Sequence

import httpx

from markets.notifiers import NotifyError

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
RETRY_SECONDS = (5, 15, 40)  # four tries in about a minute

_TOKEN = re.compile(r"bot\d+:[\w-]+")


class _MaskToken(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if _TOKEN.search(message):
            record.msg, record.args = _TOKEN.sub("bot***", message), None
        return True


logging.getLogger("httpx").addFilter(_MaskToken())


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, retry_seconds: Sequence[float] = RETRY_SECONDS,
                 sleep: Callable[[float], None] = time.sleep, client: httpx.Client | None = None):
        self._url = API_URL.format(token=token)
        self._chat_id = chat_id
        self._retry_seconds = retry_seconds
        self._sleep = sleep
        self._client = client or httpx.Client(timeout=15)

    def send(self, text: str) -> None:
        """Send one message, retrying a few times; raises NotifyError (without the token) if it never goes."""
        error = ""
        for attempt, wait in enumerate((*self._retry_seconds, None)):
            try:
                resp = self._client.post(self._url, json={"chat_id": self._chat_id, "text": text})
                if resp.status_code == 200 and resp.json().get("ok"):
                    return
                error = f"Telegram answered {resp.status_code}: {resp.json().get('description', '')}"[:200]
                if resp.status_code in (400, 401, 403, 404):  # bad token or chat id: retrying won't help
                    break
            except (httpx.HTTPError, ValueError) as exc:
                error = f"Telegram unreachable: {exc.__class__.__name__}"
            if wait is not None:
                self._sleep(wait)
        raise NotifyError(error)

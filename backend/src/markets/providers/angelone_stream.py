"""Angel One market-data WebSocket (SmartStream 2.0) as a LiveFeed.

Docs: https://smartapi.angelone.in/docs/WebSocket2 (summary in the angelone-smartapi skill, websocket-v2.md).
- Auth: the jwt and feed token of a normal REST login, sent as headers (`AngelOneProvider.stream_auth`).
- Limits, measured 20 Nov 2026: 1000 subscriptions per connection (a request that would pass it is rejected
  whole, error E1002), 3 connections per client code. A second login does not end the first session.
- Each subscribed token sends its latest quote at once, also after hours (then stamped with its last trade).
- Binary packets, little-endian, prices in paise. Quote mode (2) packets are 123 bytes; `close` is the previous
  session's close. After the closing session the last price equals the official close.

The SDK's SmartWebSocketV2 is not used: it keeps subscriptions on the class (shared by every instance),
reconnects recursively only on errors, and logs every message.
"""

from __future__ import annotations

import json
import logging
import struct
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Sequence

from markets.core.models import LiveTick
from markets.providers import ProviderError

log = logging.getLogger(__name__)

STREAM_URL = "wss://smartapisocket.angelone.in/smart-stream"
QUOTE_MODE = 2
EXCHANGE_TYPES = {"NSE": 1, "NFO": 2, "BSE": 3, "BFO": 4, "MCX": 5}
_EXCHANGES = {code: name for name, code in EXCHANGE_TYPES.items()}
MAX_SUBSCRIPTIONS = 1000
PING_SECONDS = 10  # the SDK's heartbeat
OPEN_TIMEOUT = 15.0
_IST = timezone(timedelta(hours=5, minutes=30))
_QUOTE_LEN = 123


def parse_quote_packet(data: bytes) -> Optional[LiveTick]:
    """One binary packet (LTP or Quote mode) -> LiveTick; None for packets that can't be one.
    Zero prices mean "none yet" (e.g. no trade today) and come back as None; a zero last price drops the tick."""
    if len(data) < 51:
        return None
    exchange = _EXCHANGES.get(data[1])
    token = data[2:27].split(b"\0", 1)[0].decode("ascii", "replace")
    ts_ms, ltp = struct.unpack_from("<qq", data, 35)
    if exchange is None or not token or ltp <= 0:
        return None
    fields = {}
    if len(data) >= _QUOTE_LEN:
        (volume,) = struct.unpack_from("<q", data, 67)
        prices = struct.unpack_from("<qqqq", data, 91)  # open, high, low, previous close
        fields = dict(zip(("open", "high", "low", "prev_close"), (p / 100 if p > 0 else None for p in prices)),
                      volume=float(volume))
    ts = datetime.fromtimestamp(ts_ms / 1000, _IST).replace(tzinfo=None)
    return LiveTick(exchange=exchange, token=token, ts=ts, ltp=ltp / 100, **fields)


class AngelOneStream:
    """One WebSocket connection in Quote mode. `auth` returns the connection headers (logs in if needed)."""

    max_subscriptions = MAX_SUBSCRIPTIONS

    def __init__(self, auth: Callable[[], dict[str, str]]):
        self._auth = auth
        self._ws = None
        self._thread: Optional[threading.Thread] = None
        self._closing = False

    def connect(self, on_tick: Callable[[LiveTick], None], on_close: Callable[[], None]) -> None:
        import websocket

        self.close()
        headers = self._auth()
        opened = threading.Event()
        errors: list[str] = []

        def on_data(ws, data, opcode, _more) -> None:
            if opcode == websocket.ABNF.OPCODE_BINARY:
                tick = parse_quote_packet(data)
                if tick is not None:
                    try:
                        on_tick(tick)
                    except Exception:  # never let a consumer bug kill the connection
                        log.exception("live tick handler failed")
                return
            text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
            if text != "pong":
                log.warning("Angel One stream message: %s", text[:300])  # e.g. E1002 subscription limit

        def on_error(ws, exc) -> None:
            errors.append(str(exc))

        def on_closed(ws, code, reason) -> None:
            if opened.is_set() and not self._closing:
                log.warning("Angel One stream closed (%s %s; %s)", code, reason, "; ".join(errors[-2:]) or "no error")
                on_close()

        self._closing = False
        self._ws = websocket.WebSocketApp(STREAM_URL, header=headers, on_open=lambda ws: opened.set(),
                                          on_data=on_data, on_error=on_error, on_close=on_closed)
        self._thread = threading.Thread(target=self._ws.run_forever, kwargs={"ping_interval": PING_SECONDS},
                                        name="angelone-stream", daemon=True)
        self._thread.start()
        if not opened.wait(OPEN_TIMEOUT):
            self.close()
            raise ProviderError(f"Angel One stream did not open: {'; '.join(errors) or 'timed out'}")

    def subscribe(self, refs: Sequence[tuple[str, str]]) -> None:
        tokens: dict[int, list[str]] = {}
        for exchange, token in refs:
            code = EXCHANGE_TYPES.get(exchange.upper())
            if code is not None:
                tokens.setdefault(code, []).append(token)
        if not tokens or self._ws is None:
            return
        request = {"action": 1, "params": {"mode": QUOTE_MODE, "tokenList": [
            {"exchangeType": code, "tokens": toks} for code, toks in tokens.items()]}}
        try:
            self._ws.send(json.dumps(request))
        except Exception as exc:  # the socket dropped; its on_close follows
            raise ProviderError(f"Angel One stream subscribe failed: {exc}") from exc

    def close(self) -> None:
        self._closing = True
        if self._ws is not None:
            self._ws.close()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(5)
        self._ws = self._thread = None

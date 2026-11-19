"""Price alerts: each fires once, when the live price reaches its level from the chosen side.

Every live quote is checked against the active alerts held in memory (`LiveService` listener, on the feed's
thread, so it stays cheap). Only today's quotes within the session (09:15-15:30) count: the stream replays the
previous day's last price on subscribing, and that must never fire an alert. An alert that is already met when
created or edited fires on the next such quote.

A hit leaves the in-memory list at once; the service's own thread then marks it triggered in the DB (which
succeeds only once, so a message can't go twice) and runs `handlers` with the fired alert. The Telegram
message is the first handler; another action later (an order, a webhook) is one more handler. The UI sees
fired alerts by polling GET /api/alerts. While alerts are active, the user also gets a message when the live
feed has been lost for 30 s during the session (alerts aren't checked then) and when it's back.
"""

from __future__ import annotations

import logging
import math
import queue
import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from markets.core.ports import InstrumentRepository, Notifier
from markets.pipelines.live import SESSION_HOURS, LiveService, within_hours
from markets.storage.duckdb.repositories import DuckAlertRepository

log = logging.getLogger(__name__)

DIRECTIONS = ("above", "below")
MAX_NOTE = 200
LOST_NOTICE_AFTER = timedelta(seconds=30)


class AlertFiredError(Exception):
    """The alert has already fired, so it can't be edited."""


def is_hit(direction: str, level: float, price: float) -> bool:
    """At or beyond the level, so a price that jumps over it counts."""
    return price >= level if direction == "above" else price <= level


def indian(value: float) -> str:
    """Two decimals with Indian digit grouping, as the app shows prices: 2,980.00, 1,40,000.50."""
    whole, fraction = f"{abs(value):.2f}".split(".")
    head, groups = whole[:-3], [whole[-3:]]
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return f"{'-' if value < 0 else ''}{','.join(groups)}.{fraction}"


def message(alert: dict[str, Any], price: float, ts: datetime, prev_close: Optional[float]) -> str:
    """The Telegram text: what fired, the price and time, the day's change, when it was set and its note."""
    name = alert["symbol"][:-3] if alert["symbol"].endswith("-EQ") else alert["symbol"]
    rupee = "₹" if alert["instrument_type"] == "EQ" else ""
    day = f" · {price / prev_close - 1:+.2%} today" if prev_close else ""
    created = alert["created_at"]
    note = f' · "{alert["note"]}"' if alert.get("note") else ""
    return (f"🔔 {name} {alert['direction']} {rupee}{indian(alert['price'])}\n"
            f"LTP {rupee}{indian(price)} at {ts:%H:%M:%S}{day}\n"
            f"Alert set {created.day} {created:%b}{note}")


def _clean(direction: str, price: float, note: Optional[str]) -> tuple[str, float, Optional[str]]:
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {', '.join(DIRECTIONS)}")
    if not (isinstance(price, (int, float)) and math.isfinite(price) and price > 0):
        raise ValueError("price must be above 0")
    note = (note or "").strip() or None
    if note and len(note) > MAX_NOTE:
        raise ValueError(f"note is longer than {MAX_NOTE} characters")
    return direction, float(price), note


class AlertService:
    def __init__(self, repo: DuckAlertRepository, instruments: InstrumentRepository, live: LiveService,
                 notifier: Optional[Notifier], clock: Callable[[], datetime] = datetime.now):
        self._repo = repo
        self._instruments = instruments
        self._live = live
        self._notifier = notifier
        self._clock = clock
        self.handlers: list[Callable[[dict[str, Any]], None]] = [self._send_message]
        self._lock = threading.Lock()
        self._active: dict[int, list[dict[str, Any]]] = {}
        self._events: "queue.Queue[tuple[dict[str, Any], dict[str, Any]]]" = queue.Queue()
        self._told_lost = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._reload()
        live.add_listener(self.on_quote)

    @property
    def telegram(self) -> bool:
        return self._notifier is not None

    # ---- API side ----------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        return self._repo.all()

    def instrument_ids(self) -> list[int]:
        """Stocks with an active alert: streamed all day."""
        with self._lock:
            return list(self._active)

    def create(self, instrument_id: int, direction: str, price: float, note: Optional[str] = None) -> dict[str, Any]:
        direction, price, note = _clean(direction, price, note)
        if self._instruments.get(instrument_id) is None:
            raise KeyError(f"instrument {instrument_id} not found")
        alert_id = self._repo.create(instrument_id, direction, price, note, self._clock())
        self._after_change(instrument_id)
        return self._repo.get(alert_id)

    def update(self, alert_id: str, direction: str, price: float, note: Optional[str] = None) -> dict[str, Any]:
        direction, price, note = _clean(direction, price, note)
        alert = self._repo.get(alert_id)
        if alert is None:
            raise KeyError(f"alert {alert_id} not found")
        if not self._repo.update(alert_id, direction, price, note):
            raise AlertFiredError("this alert has already fired")
        self._after_change(alert["instrument_id"])
        return self._repo.get(alert_id)

    def delete(self, alert_id: str) -> bool:
        deleted = self._repo.delete(alert_id)
        if deleted:
            self._reload()
        return deleted

    def _after_change(self, instrument_id: int) -> None:
        """Reload the in-memory list, stream the stock, and check its current price at once."""
        self._reload()
        self._live.watch([instrument_id])
        for quote in self._live.quotes([instrument_id]):
            self.on_quote(instrument_id, quote)

    def _reload(self) -> None:
        active: dict[int, list[dict[str, Any]]] = {}
        for alert in self._repo.active():
            active.setdefault(alert["instrument_id"], []).append(alert)
        with self._lock:
            self._active = active

    # ---- feed thread -------------------------------------------------------------

    def on_quote(self, instrument_id: int, quote: dict[str, Any]) -> None:
        ts = quote["ts"]
        if ts.date() != self._clock().date() or not within_hours(ts, SESSION_HOURS):
            return
        with self._lock:
            alerts = self._active.get(instrument_id)
            if not alerts:
                return
            hits = [a for a in alerts if is_hit(a["direction"], a["price"], quote["ltp"])]
            if not hits:
                return
            remaining = [a for a in alerts if a not in hits]
            if remaining:
                self._active[instrument_id] = remaining
            else:
                del self._active[instrument_id]
        for alert in hits:
            self._events.put((alert, quote))

    # ---- service thread ----------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="alerts", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(10)
            self._thread = None

    def _run(self) -> None:
        for alert in self._repo.unnotified():  # fired just before the app last stopped
            self._send_message({**alert, "quote": None})
        while not self._stop.is_set():
            try:
                self.process(timeout=1.0)
            except Exception:
                log.exception("alerts step failed")

    def process(self, timeout: float = 0.0) -> None:
        """Fire every queued hit (waiting up to `timeout` for one), then check the live feed's state."""
        try:
            while True:
                self._fire(*self._events.get(timeout=timeout))
                timeout = 0.0
        except queue.Empty:
            pass
        self._watch_feed()

    def _fire(self, alert: dict[str, Any], quote: dict[str, Any]) -> None:
        if not self._repo.mark_triggered(alert["alert_id"], quote["ts"], quote["ltp"]):
            return  # deleted or edited away in the meantime, or already fired
        fired = {**alert, "triggered_at": quote["ts"], "triggered_price": quote["ltp"], "quote": quote}
        log.info("alert fired: %s %s %s at %s", alert["symbol"], alert["direction"], alert["price"], quote["ltp"])
        for handler in self.handlers:
            try:
                handler(fired)
            except Exception:
                log.exception("alert handler failed")

    def _send_message(self, fired: dict[str, Any]) -> None:
        if self._notifier is None:
            self._repo.set_notified(fired["alert_id"], "off")
            return
        quote = fired.get("quote") or {}
        try:
            self._notifier.send(message(fired, fired["triggered_price"], fired["triggered_at"], quote.get("prev_close")))
        except Exception as exc:
            log.warning("alert message failed: %s", exc)
            self._repo.set_notified(fired["alert_id"], "failed", str(exc)[:200])
            return
        self._repo.set_notified(fired["alert_id"], "sent")

    def _watch_feed(self) -> None:
        """While alerts are active, tell the user when the feed is lost for a while in the session, and when
        it's back (only after a 'lost' message)."""
        if self._notifier is None:
            return
        status = self._live.status()
        if not self._told_lost:
            lost_at = status["lost_at"]
            if (status["session_open"] and not status["connected"] and lost_at is not None
                    and self._clock() - lost_at >= LOST_NOTICE_AFTER and self.instrument_ids()):
                self._told_lost = self._try_send(
                    f"⚠️ Live feed lost at {lost_at:%H:%M:%S}: alerts aren't being checked until it's back.")
        elif status["connected"]:
            if self._try_send(f"✅ Live feed back at {self._clock():%H:%M:%S}: alerts are being checked again."):
                self._told_lost = False

    def _try_send(self, text: str) -> bool:
        try:
            self._notifier.send(text)
            return True
        except Exception as exc:
            log.warning("feed notice failed: %s", exc)
            return False

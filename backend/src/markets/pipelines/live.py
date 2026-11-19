"""Live quotes: one streaming connection during market hours, the latest quote per instrument in memory.

Nothing is written to the database. Stored daily bars stay the nightly job's: a stock's official close (a
weighted average of the last 30 minutes) only matches the streamed last price after the closing session.
The UI shows a live quote only while it is newer than the stored daily bar, so the official bar takes over
by itself once the nightly update has stored it.

What streams: `base_ids` (read on every connect: benchmarks and your own lists) plus whatever the UI asks
for through `watch` (the chart's stock, ...), for the rest of the day. All feed calls run on the service's
own thread, so a slow connect never holds up an API request.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Iterable, Optional

from markets.core.models import LiveTick
from markets.core.ports import InstrumentRepository, LiveFeed

log = logging.getLogger(__name__)

# Connected from pre-open until after the closing session (its last quotes arrive around 16:08).
FEED_HOURS = (time(9, 0), time(16, 15))
SESSION_HOURS = (time(9, 15), time(15, 30))
RETRY_SECONDS = (5, 10, 30, 60)


def _within(now: datetime, hours: tuple[time, time]) -> bool:
    return now.weekday() < 5 and hours[0] <= now.time() < hours[1]


class LiveService:
    def __init__(self, feed: LiveFeed, instruments: InstrumentRepository, provider: str,
                 base_ids: Callable[[], Iterable[int]], clock: Callable[[], datetime] = datetime.now):
        self._feed = feed
        self._instruments = instruments
        self._provider = provider
        self._base_ids = base_ids
        self._clock = clock
        self._lock = threading.Lock()  # guards _wanted and _quotes/_last_tick (touched by API and feed threads)
        self._wanted: set[int] = set()  # asked for through watch() on _wanted_day
        self._wanted_day: Optional[date] = None
        self._streamed: set[int] = set()  # subscribed on the current connection
        self._refs: dict[int, Optional[tuple[str, str]]] = {}  # instrument -> (exchange, token); None = can't stream
        self._ids_by_ref: dict[tuple[str, str], int] = {}
        self._quotes: dict[int, dict[str, Any]] = {}
        self._last_tick: Optional[datetime] = None
        self._day: Optional[date] = None
        self._connected = False
        self._lost_at: Optional[datetime] = None
        self._retry_at: Optional[datetime] = None
        self._failures = 0
        self._full_logged = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- API side ----------------------------------------------------------------

    def watch(self, instrument_ids: Iterable[int]) -> None:
        """Stream these for the rest of the day (subscribed within a second while connected)."""
        with self._lock:
            self._roll_day(self._clock().date())
            self._wanted.update(instrument_ids)

    def _roll_day(self, today: date) -> None:
        """Forget stocks asked for on earlier days (caller holds the lock)."""
        if self._wanted_day != today:
            self._wanted_day = today
            self._wanted.clear()

    def quotes(self, instrument_ids: Iterable[int]) -> list[dict[str, Any]]:
        """Latest quote of each instrument that has one (any day: compare `ts` with the stored bars)."""
        with self._lock:
            return [{"instrument_id": i, **self._quotes[i]} for i in instrument_ids if i in self._quotes]

    def status(self) -> dict[str, Any]:
        now = self._clock()
        return {
            "connected": self._connected,
            "session_open": _within(now, SESSION_HOURS),
            "today": now.date().isoformat(),
            "last_tick": self._last_tick,
            "lost_at": self._lost_at,
        }

    # ---- lifecycle ---------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="live-feed", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(20)
            self._thread = None
        self._disconnect()

    def _run(self) -> None:
        while not self._stop.wait(1.0):
            try:
                self.step()
            except Exception:
                log.exception("live feed step failed")

    def step(self) -> None:
        """One pass of the loop: connect during feed hours (retrying after a drop), subscribe what's
        wanted, disconnect outside feed hours."""
        now = self._clock()
        if not _within(now, FEED_HOURS):
            if self._connected:
                self._disconnect()
                log.info("live feed closed for the day")
            self._lost_at, self._retry_at, self._failures = None, None, 0
            return
        with self._lock:
            self._roll_day(now.date())
        if self._day != now.date():  # a new day: look tokens up afresh
            self._day = now.date()
            self._refs.clear()
            self._ids_by_ref.clear()
            self._full_logged = False
        if not self._connected:
            if self._retry_at is not None and now < self._retry_at:
                return
            if not self._connect(now):
                return
        self._subscribe_wanted()

    def _connect(self, now: datetime) -> bool:
        try:
            self._feed.connect(self._on_tick, self._on_drop)
        except Exception as exc:
            self._feed.close()
            self._failures += 1
            delay = RETRY_SECONDS[min(self._failures, len(RETRY_SECONDS)) - 1]
            self._retry_at = now + timedelta(seconds=delay)
            self._lost_at = self._lost_at or now
            if self._failures == 1 or self._failures % 10 == 0:
                log.warning("live feed connect failed (%d in a row, next try in %ds): %s", self._failures, delay, exc)
            return False
        self._connected, self._streamed = True, set()
        self._lost_at, self._retry_at, self._failures = None, None, 0
        with self._lock:
            self._wanted.update(self._base_ids())
        log.info("live feed connected")
        return True

    def _subscribe_wanted(self) -> None:
        with self._lock:
            pending = sorted(self._wanted - self._streamed)
        refs, ids = [], []
        for i in pending:
            ref = self._ref(i)
            if ref is None:
                continue
            if len(self._streamed) + len(ids) >= self._feed.max_subscriptions:
                if not self._full_logged:
                    log.warning("live feed full (%d instruments); not streaming the rest", self._feed.max_subscriptions)
                    self._full_logged = True
                break
            refs.append(ref)
            ids.append(i)
        if refs:
            self._feed.subscribe(refs)
            self._streamed.update(ids)

    def _ref(self, instrument_id: int) -> Optional[tuple[str, str]]:
        if instrument_id not in self._refs:
            instrument = self._instruments.get(instrument_id)
            token = self._instruments.provider_token(instrument_id, self._provider)
            ref = (instrument.exchange.upper(), token) if instrument and token else None
            self._refs[instrument_id] = ref
            if ref:
                self._ids_by_ref[ref] = instrument_id
        return self._refs[instrument_id]

    def _disconnect(self) -> None:
        self._feed.close()
        self._connected, self._streamed = False, set()

    # ---- feed thread -------------------------------------------------------------

    def _on_tick(self, tick: LiveTick) -> None:
        instrument_id = self._ids_by_ref.get((tick.exchange.upper(), tick.token))
        if instrument_id is None:
            return
        quote = {"ts": tick.ts, "ltp": tick.ltp, "open": tick.open, "high": tick.high, "low": tick.low,
                 "prev_close": tick.prev_close, "volume": tick.volume}
        with self._lock:
            self._quotes[instrument_id] = quote
            if self._last_tick is None or tick.ts > self._last_tick:
                self._last_tick = tick.ts

    def _on_drop(self) -> None:
        now = self._clock()
        self._connected, self._streamed = False, set()
        self._lost_at = self._lost_at or now
        self._retry_at = now + timedelta(seconds=RETRY_SECONDS[0])
        log.warning("live feed lost; reconnecting")

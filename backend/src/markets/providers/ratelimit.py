from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Sequence


class RateLimiter:
    """Blocks until a call fits every (max_calls, per_seconds) window.

    Angel One limits requests per second, per minute and per hour at once; a single fixed
    gap cannot respect all three without being slow, a sliding window can.
    """

    def __init__(self, limits: Sequence[tuple[int, float]], clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self._limits = sorted(limits, key=lambda l: l[1])
        self._horizon = max(per for _, per in limits)
        self._calls: deque[float] = deque()
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            while True:
                now = self._clock()
                while self._calls and now - self._calls[0] >= self._horizon:
                    self._calls.popleft()
                wait = 0.0
                for max_calls, per in self._limits:
                    in_window = [t for t in self._calls if now - t < per]
                    if len(in_window) >= max_calls:
                        # The slot frees up when the oldest call that still counts expires.
                        oldest = in_window[len(in_window) - max_calls]
                        wait = max(wait, per - (now - oldest))
                if wait <= 0:
                    self._calls.append(now)
                    return
                self._sleep(wait + 0.01)

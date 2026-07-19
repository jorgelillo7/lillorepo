"""Tiny in-process rate limiter for abuse basics on public endpoints.

Per-instance state only — Cloud Run instances don't share it. That is the
point: this blunts bursts and dumb bots at zero cost, it is not a
bookkeeping-grade quota system.
"""

import time
from collections import deque


class RateLimiter:
    """Sliding-window counter: at most `max_events` per `window_seconds`
    per key (typically the client IP)."""

    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._events: dict[str, deque] = {}

    def allow(self, key: str) -> bool:
        """Record an attempt for `key`; False when the window is full."""
        now = time.monotonic()
        window = self._events.setdefault(key, deque())
        while window and now - window[0] > self.window_seconds:
            window.popleft()
        if len(window) >= self.max_events:
            return False
        window.append(now)
        # Opportunistic pruning keeps the dict from growing unbounded on
        # one-off keys (each entry is just a deque of floats).
        if len(self._events) > 10_000:
            self._events = {k: q for k, q in self._events.items() if q}
        return True

    def reset(self) -> None:
        self._events.clear()

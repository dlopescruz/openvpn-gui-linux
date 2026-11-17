"""Speed (bytes/s) calculation from OpenVPN byte counters. No Qt."""
from __future__ import annotations

import math
import time
from collections import deque


def human_rate(bps: float) -> str:
    for unit, size in (("GB/s", 1 << 30), ("MB/s", 1 << 20), ("KB/s", 1 << 10)):
        if bps >= size:
            return f"{bps / size:.1f} {unit}"
    return f"{bps:.0f} B/s"


def nice_ceiling(value: float) -> float:
    """Round up to 1, 2, 5 or 10 x a power of ten (a 'nice' chart scale)."""
    exp = 10 ** math.floor(math.log10(value))
    for m in (1, 2, 5, 10):
        if value <= m * exp:
            return m * exp
    return 10 * exp


class RateTracker:
    """Keeps the last `window` download and upload speeds."""

    def __init__(self, window: int = 120):
        self.window = window
        self.down: deque[float] = deque(maxlen=window)
        self.up: deque[float] = deque(maxlen=window)
        self._last: tuple[float, int, int] | None = None

    def reset(self) -> None:
        self.down.clear()
        self.up.clear()
        self._last = None

    def add(self, rx_total: int, tx_total: int, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if self._last is not None:
            t0, rx0, tx0 = self._last
            dt = max(now - t0, 0.2)
            # counter lower than the previous one = a reconnect reset the totals -> speed 0
            self.down.append(max(rx_total - rx0, 0) / dt)
            self.up.append(max(tx_total - tx0, 0) / dt)
        self._last = (now, rx_total, tx_total)

    def latest(self) -> tuple[float, float]:
        return (self.down[-1] if self.down else 0.0, self.up[-1] if self.up else 0.0)

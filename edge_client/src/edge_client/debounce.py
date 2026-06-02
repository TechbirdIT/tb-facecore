"""Per-device punch debounce (in-memory, time injected for testability)."""

from __future__ import annotations

from datetime import datetime, timedelta


class Debouncer:
    def __init__(self, window_minutes: int) -> None:
        self.window = timedelta(minutes=window_minutes)
        self._last: dict[str, datetime] = {}

    def allow(self, device_id: str, now: datetime) -> bool:
        last = self._last.get(device_id)
        if last is not None and now - last < self.window:
            return False
        self._last[device_id] = now
        return True

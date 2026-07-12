"""Accumulates device on-time.

Two counters per channel:
  * `today`    -- usage since local midnight, for the user-facing "used today" sensors.
  * `lifetime` -- total on-time, for filter life / maintenance (never resets).

The sensors persist both across restarts (they restore the totals and seed them back
here), so a restart doesn't lose today's usage or reset the filter counter.
"""
from __future__ import annotations


class RuntimeTracker:
    def __init__(self) -> None:
        self._last: float | None = None
        self._active: set[str] = set()
        self.seconds: dict[str, float] = {}        # lifetime
        self.today_seconds: dict[str, float] = {}  # since midnight
        self._day: str | None = None

    def update(self, now: float, active: set[str], day: str | None = None) -> None:
        if self._last is not None:
            elapsed = max(0.0, now - self._last)
            for channel in self._active:  # what ran during the just-elapsed interval
                self.seconds[channel] = self.seconds.get(channel, 0.0) + elapsed
                self.today_seconds[channel] = self.today_seconds.get(channel, 0.0) + elapsed
        # Roll over *after* accruing, so the interval that straddles midnight is booked
        # to the day that just ended and the new day starts clean.
        if day is not None and day != self._day:
            if self._day is not None:
                self.today_seconds = {}
            self._day = day
        self._last = now
        self._active = set(active)

    def seed(self, channel: str, hours: float) -> None:
        """Restore the persisted lifetime total (filter life must survive restarts)."""
        self.seconds[channel] = max(self.seconds.get(channel, 0.0), hours * 3600.0)

    def seed_today(self, channel: str, hours: float, day: str) -> None:
        """Restore today's usage, but only if the persisted value is from today."""
        if self._day is not None and self._day != day:
            return
        self._day = day
        self.today_seconds[channel] = max(self.today_seconds.get(channel, 0.0), hours * 3600.0)

    @property
    def day(self) -> str | None:
        """The local date the daily counters belong to."""
        return self._day

    def hours(self, channel: str) -> float:
        """Lifetime on-time in hours."""
        return round(self.seconds.get(channel, 0.0) / 3600.0, 3)

    def today_hours(self, channel: str) -> float:
        """On-time since local midnight, in hours."""
        return round(self.today_seconds.get(channel, 0.0) / 3600.0, 3)

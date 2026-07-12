"""Peak-hold with exponential decay.

Holds a signal near its recent peak and lets it decay toward the live value over a
half-life, so a spike keeps driving output through its tail rather than collapsing
the instant the raw reading dips. Stateful (the peak persists across cycles); fed a
monotonic timestamp each update so it is straightforward to test.
"""
from __future__ import annotations


class PeakDecay:
    def __init__(self) -> None:
        self._peak = 0.0
        self._ts: float | None = None

    def update(self, value: float, now: float, half_life_s: float) -> float:
        """Return max(value, decayed-peak). half_life_s <= 0 disables the hold."""
        value = max(0.0, float(value))
        if self._ts is None or half_life_s <= 0:
            self._peak, self._ts = value, now
            return value
        elapsed = max(0.0, now - self._ts)
        decayed = self._peak * 0.5 ** (elapsed / half_life_s)
        held = max(value, decayed)
        self._peak, self._ts = held, now
        return held

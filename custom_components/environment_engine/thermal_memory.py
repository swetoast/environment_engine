"""Short-term memory: which way the room is moving right now.

Deliberately small. Anything that needs to *understand* the room -- how sluggish it is,
how much the sun adds, what the AC achieves -- belongs to `thermal_model`, which fits the
physics properly. This only answers "warmer or cooler than a moment ago", which the
learned model cannot: it reports steady-state behaviour, not the last few minutes.
"""
from __future__ import annotations
from dataclasses import dataclass

_MAX_GAP_MIN = 30.0      # longer than this is a restart or an outage, not a trend
_SPIKE_C = 5.0           # a room does not move this fast; that is a sensor glitch
# EMA weight on the newest reading. 0.25 keeps a +/-0.05 C noisy sensor peaking around
# 0.015 C/min -- comfortably under the 0.025 threshold -- while still recognising a room
# warming at 3 C/hour within three samples. At 0.4 the noise alone crossed the line.
_SMOOTHING = 0.25


@dataclass(slots=True)
class ThermalMemory:
    previous_indoor: float | None = None
    previous_humidity: float | None = None
    thermal_inertia: float = 0.0
    temperature_trend: float = 0.0
    humidity_trend: float = 0.0


class ThermalMemoryEngine:
    def __init__(self) -> None:
        self.memory = ThermalMemory()

    def update(self, indoor, humidity, outdoor, valid: bool = True,
               dt_minutes: float | None = None) -> ThermalMemory:
        """Fold one reading into the trends.

        `valid` is the temperature sensor's own verdict. When a sensor drops out the
        coordinator substitutes a placeholder, and folding that in produced a fake trend
        of tens of degrees -- which then drove a real setpoint drop and a real confidence
        bonus. The reading is skipped instead, and the previous value is dropped so the
        gap does not become a trend when the sensor comes back either.
        """
        memory = self.memory
        if indoor is None or not valid:
            memory.previous_indoor = None
            memory.temperature_trend = 0.0
            return memory

        usable = (
            memory.previous_indoor is not None
            and abs(indoor - memory.previous_indoor) <= _SPIKE_C
            and (dt_minutes is None or 0.0 < dt_minutes <= _MAX_GAP_MIN)
        )
        if usable:
            # Per-interval delta normalised to a nominal minute, then smoothed. Without
            # the normalisation the trend scaled with whatever update_interval happened to
            # be; without the smoothing, sensor noise *was* the trend.
            span = dt_minutes if dt_minutes else 1.0
            delta = (indoor - memory.previous_indoor) / span
            memory.temperature_trend = (1 - _SMOOTHING) * memory.temperature_trend + _SMOOTHING * delta
        memory.previous_indoor = indoor

        if humidity is None:
            memory.previous_humidity = None
            memory.humidity_trend = 0.0
        else:
            if memory.previous_humidity is not None:
                delta = humidity - memory.previous_humidity
                memory.humidity_trend = (1 - _SMOOTHING) * memory.humidity_trend + _SMOOTHING * delta
            memory.previous_humidity = humidity

        # How far the room sits from the outdoors, 0..1. This is a *load* signal -- a big
        # gap means the envelope is working hard -- not the room's thermal mass, which the
        # learned model measures properly as its time constant.
        if outdoor is not None:
            memory.thermal_inertia = min(abs(indoor - outdoor) / 10.0, 1.0)
        return memory

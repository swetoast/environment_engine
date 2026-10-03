"""Temperature unit normalization.

The engine reasons in Celsius internally. Sensors and climate entities may
report in Fahrenheit or Kelvin (a sensor's own unit can even differ from the
system unit), so values are converted to Celsius on read and back to the target
device's unit on write. Without this, a Fahrenheit sensor reading 77 would feed
the thermal math as if the room were 77 C and pin the engine at maximum cooling.
"""
from __future__ import annotations


def _canon(unit: str | None) -> str:
    return (unit or "").strip().lower().lstrip("°")


def to_celsius(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    u = _canon(unit)
    if u in ("f", "fahrenheit"):
        return (value - 32.0) * 5.0 / 9.0
    if u in ("k", "kelvin"):
        return value - 273.15
    return value


def from_celsius(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    u = _canon(unit)
    if u in ("f", "fahrenheit"):
        return value * 9.0 / 5.0 + 32.0
    if u in ("k", "kelvin"):
        return value + 273.15
    return value

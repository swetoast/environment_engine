"""Small psychrometric helpers."""
from __future__ import annotations
import math

_A = 17.625
_B = 243.04


def dew_point(temp_c: float | None, relative_humidity: float | None) -> float | None:
    """Dew point (°C) from air temperature and relative humidity via the Magnus
    formula. Returns None if inputs are missing or out of range. Cooling room air
    toward its dew point risks condensation on cold surfaces."""
    if temp_c is None or relative_humidity is None or relative_humidity <= 0:
        return None
    rh = min(float(relative_humidity), 100.0)
    gamma = math.log(rh / 100.0) + _A * temp_c / (_B + temp_c)
    denom = _A - gamma
    if denom == 0:
        return None
    return _B * gamma / denom


def feels_like(temp_c: float | None, relative_humidity: float | None, max_bump: float) -> float | None:
    """Perceived ('feels-like') temperature (°C): humid air feels warmer, so this
    adds a bounded bump above ~20 °C that grows with warmth and humidity. Below
    that, or with no humidity reading, it returns the dry-bulb temperature. The
    bump is capped at `max_bump` so it stays a gentle nudge, never a runaway.
    """
    if temp_c is None:
        return None
    if relative_humidity is None or temp_c < 20.0 or max_bump <= 0:
        return temp_c
    excess_rh = max(0.0, min(float(relative_humidity), 100.0) - 40.0)  # RH above 40%
    warmth = max(0.0, min((temp_c - 20.0) / 10.0, 1.0))                # 0 at 20 °C, 1 at 30 °C+
    bump = (excess_rh / 60.0) * warmth * max_bump
    return temp_c + min(bump, max_bump)

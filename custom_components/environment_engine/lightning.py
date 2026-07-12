"""Dynamic lightning hold from Blitzortung geo_location strikes.

Gated by config: the user points at a Blitzortung sensor in the Global setup to
confirm the integration is installed; only then does the coordinator scan the
per-strike ``geo_location.lightning_strike_*`` entities and feed their distances
and ages here. The hold window and reaction radius scale with storm intensity
(strike count) and proximity, auto-releasing as strikes age out.
"""
from __future__ import annotations


def lightning_hold(distances_km, ages_s, max_react_km):
    """Return (hold, closest_km, strikes).

    * intensity = (strikes-1)/9 clamped 0..1
    * window 300 .. 1800 s, radius 10 .. 50 km (scale with intensity)
    * fade = (1 - closest/radius) ** (4 .. 0.7)  (proximity; flattens with intensity)
    * hold when the newest strike is within max_react_km and its age <= window*fade
    """
    distances_km = [d for d in (distances_km or []) if d is not None]
    if not distances_km:
        return False, None, 0
    strikes = len(distances_km)
    closest = min(distances_km)
    ages = [a for a in (ages_s or []) if a is not None]
    age = min(ages) if ages else None
    if age is None or closest > max_react_km:
        return False, closest, strikes
    intensity = max(0.0, min((strikes - 1) / 9.0, 1.0))
    window = 300 + intensity * 1500
    radius = 10 + intensity * 40
    d_norm = min(closest / radius, 0.99) if radius > 0 else 1.0
    exponent = 4 + intensity * -3.3
    fade = (1 - d_norm) ** exponent
    return age <= window * fade, closest, strikes

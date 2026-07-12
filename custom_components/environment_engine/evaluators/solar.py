from __future__ import annotations
from dataclasses import dataclass
from ..confidence import clamp
@dataclass(slots=True)
class SolarResult:
    pressure: float       # heat-based solar load, independent of blind position
    shading_recommended: bool
    reason: str


def evaluate_solar(snapshot, options) -> SolarResult:
    if not snapshot.sun_up:
        return SolarResult(0.0, False, "sun is down")
    heat = clamp((snapshot.outdoor_temp - 20.0) / 15.0) if snapshot.outdoor_temp is not None else 0.0
    lux_shade = False
    if snapshot.lux is not None:
        threshold = float(options.lux_threshold)
        # Low sun -> horizontal light -> more glare/gain, so shade at a lower
        # measured-light threshold (solar-geometry-aware).
        if snapshot.sun_elevation is not None and snapshot.sun_elevation < 30:
            threshold *= max(0.5, snapshot.sun_elevation / 30.0)
        lux_shade = snapshot.lux >= threshold
    shading = heat >= 0.35 or lux_shade
    if lux_shade:
        low = snapshot.sun_elevation is not None and snapshot.sun_elevation < 30
        reason = "low-angle sun glare; shading early" if low else "measured light is high; shading reduces glare and gain"
    elif heat >= 0.35:
        reason = "solar heat load supports shading"
    else:
        reason = "solar load is low"
    return SolarResult(heat, shading, reason)

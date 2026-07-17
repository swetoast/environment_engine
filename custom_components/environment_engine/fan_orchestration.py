from __future__ import annotations
def recommended_fan_speed(pressure: float) -> str:
    if pressure >= 0.8:
        return "high"
    if pressure >= 0.5:
        return "medium"
    return "low"

from __future__ import annotations
def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(min(value, high), low)
def confidence_score(base: float, penalties: list[float] | None = None, bonuses: list[float] | None = None) -> float:
    score = base
    for bonus in bonuses or []:
        score += bonus
    for penalty in penalties or []:
        score -= penalty
    return clamp(score)
def pressure_tier(confidence: float, noun: str) -> str:
    level = "high" if confidence >= 0.65 else "moderate" if confidence >= 0.3 else "low"
    return f"{level} {noun} pressure"


def speed_tier(pressure: float, high: float, medium: float) -> str:
    """Map a 0..1 pressure to low/medium/high at the given cut points."""
    if pressure >= high:
        return "high"
    if pressure >= medium:
        return "medium"
    return "low"

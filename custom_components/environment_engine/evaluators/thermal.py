from __future__ import annotations
from dataclasses import dataclass
from ..confidence import clamp, confidence_score, pressure_tier
@dataclass(slots=True)
class ThermalResult:
    pressure: float
    confidence: float
    reason: str
def evaluate_thermal(snapshot, memory, solar_pressure: float, energy_penalty: float, learning_bias: float = 0.0, target: float = 22.0, anticipation: float = 0.0) -> ThermalResult:
    temp = snapshot.feels_like if snapshot.feels_like is not None else snapshot.indoor_temp
    # Above the setpoint is above the setpoint. The old /10 span meant confidence only
    # reached the 0.3 action threshold at +3 C, so setting 22 did nothing until 25.
    # A 1 C excess now clears it outright.
    base = clamp((temp + anticipation - target) / 3.0)  # anticipation leads a fast-warming room
    bonuses = [solar_pressure * 0.25, memory.thermal_inertia * 0.1, learning_bias]
    if memory.temperature_trend > 0.15:
        bonuses.append(0.1)
    # Price influences how HARD the engine cools (via the setpoint), never WHETHER it
    # cools. Subtracting it here meant an expensive evening pushed the cool-start point
    # from 25 C out to 28 C -- the room got hot to save money nobody agreed to spend.
    confidence = confidence_score(base, None, bonuses)
    reason = pressure_tier(confidence, "thermal")
    return ThermalResult(base, confidence, reason)

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
    base = clamp((temp + anticipation - target) / 10.0)  # anticipation leads a fast-warming room
    bonuses = [solar_pressure * 0.25, memory.thermal_inertia * 0.1, learning_bias]
    if memory.temperature_trend > 0.15:
        bonuses.append(0.1)
    confidence = confidence_score(base, [energy_penalty], bonuses)
    reason = pressure_tier(confidence, "thermal")
    return ThermalResult(base, confidence, reason)

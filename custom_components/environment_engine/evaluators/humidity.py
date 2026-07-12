from __future__ import annotations
from dataclasses import dataclass
from ..confidence import clamp, confidence_score, pressure_tier
@dataclass(slots=True)
class HumidityResult:
    pressure: float
    confidence: float
    reason: str
def evaluate_humidity(snapshot, memory, learning_bias: float = 0.0) -> HumidityResult:
    if snapshot.humidity is None:
        return HumidityResult(0.0, 0.0, "humidity sensor unavailable")
    pressure = clamp((snapshot.humidity - 55.0) / 45.0)
    bonuses = [learning_bias]
    if memory.humidity_trend > 0.5:
        bonuses.append(0.1)
    confidence = confidence_score(pressure, [], bonuses)
    reason = pressure_tier(confidence, "humidity")
    return HumidityResult(pressure, confidence, reason)

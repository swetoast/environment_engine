from __future__ import annotations
from dataclasses import dataclass
from ..confidence import clamp
@dataclass(slots=True)
class MoldResult:
    risk: float
    airflow_recommended: bool
    reason: str
def evaluate_mold(snapshot, memory) -> MoldResult:
    if snapshot.humidity is None:
        return MoldResult(0.0, False, "humidity sensor unavailable")
    cold = 0.1 if (snapshot.temperature_valid and snapshot.indoor_temp < 18.0) else 0.0
    trend = 0.1 if memory.humidity_trend > 0.5 else 0.0
    risk = clamp(((snapshot.humidity - 60.0) / 40.0) + cold + trend)
    return MoldResult(risk, risk >= 0.5, "mold risk needs airflow" if risk >= 0.5 else "mold risk is low")

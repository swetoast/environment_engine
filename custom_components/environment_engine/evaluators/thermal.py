from __future__ import annotations
from dataclasses import dataclass
from ..confidence import clamp, confidence_score, pressure_tier
from ..const import WARMING_TREND_C_PER_MIN
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
    excess = 0.0 if temp is None else temp - target
    # Anticipation lets the engine start sooner on a room it has learned warms quickly,
    # but it may only ever LEAD a decision the room is already making -- never make one on
    # its own. Without this guard a confident prediction pushed a room sitting *below* the
    # setpoint over the action threshold, and the fan would run in an already-cool room on
    # forecast alone. It also matters more than it used to: the span tightened from 10 C to
    # 3 C in the setpoint rework, so the same anticipation now counts for three times as
    # much as when it was tuned.
    lead = anticipation if excess > 0.0 else 0.0
    base = clamp((excess + lead) / 3.0)
    bonuses = [solar_pressure * 0.25, memory.thermal_inertia * 0.1, learning_bias]
    if memory.temperature_trend > WARMING_TREND_C_PER_MIN:
        bonuses.append(0.1)
    # Price influences how HARD the engine cools (via the setpoint), never WHETHER it
    # cools. Subtracting it here meant an expensive evening pushed the cool-start point
    # from 25 C out to 28 C -- the room got hot to save money nobody agreed to spend.
    confidence = confidence_score(base, None, bonuses)
    reason = pressure_tier(confidence, "thermal")
    return ThermalResult(base, confidence, reason)

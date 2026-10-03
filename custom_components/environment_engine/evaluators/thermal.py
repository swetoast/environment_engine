from __future__ import annotations
from dataclasses import dataclass
from ..confidence import clamp, confidence_score, pressure_tier
from ..const import WARMING_TREND_C_PER_MIN
@dataclass(slots=True)
class ThermalResult:
    pressure: float
    confidence: float
    reason: str
def evaluate_thermal(snapshot, memory, solar_pressure: float, energy_penalty: float, learning_bias: float = 0.0, target: float = 22.0, anticipation: float = 0.0, base: float | None = None) -> ThermalResult:
    temp = snapshot.feels_like if snapshot.feels_like is not None else snapshot.indoor_temp
    # Above the setpoint is above the setpoint. The old /10 span meant confidence only
    # reached the 0.3 action threshold at +3 C, so setting 22 did nothing until 25.
    # A 1 C excess now clears it outright.
    excess = 0.0 if temp is None else temp - target
    # `target` is the DRIVEN setpoint, which on a hot or damp day sits below the number the
    # user asked for (`base`). That lower number says how hard to cool once cooling; it
    # does not make a room at or under the user's setpoint warm. Without this the fan ran
    # at 21.9 C against a 22 C setpoint all afternoon, because the driven setpoint was 21.
    if base is not None and temp is not None and temp <= base:
        excess = 0.0
    # Anticipation lets the engine start sooner on a room it has learned warms quickly,
    # but it may only ever LEAD a decision the room is already making -- never make one on
    # its own. Without this guard a confident prediction pushed a room sitting *below* the
    # setpoint over the action threshold, and the fan would run in an already-cool room on
    # forecast alone. It also matters more than it used to: the span tightened from 10 C to
    # 3 C in the setpoint rework, so the same anticipation now counts for three times as
    # much as when it was tuned.
    lead = anticipation if excess > 0.0 else 0.0
    base = clamp((excess + lead) / 3.0)
    # The same guard applies to every bonus. Sun, inertia, a warming trend and the learned
    # bias all say "this will get worse", which only means something for a room that is
    # already above the setpoint. Added to a room below it they summed past the fan's
    # threshold on their own, so a 19 C room in winter sunshine got a fan.
    bonuses = []
    if excess > 0.0:
        bonuses = [solar_pressure * 0.25, memory.thermal_inertia * 0.1, learning_bias]
        if memory.temperature_trend > WARMING_TREND_C_PER_MIN:
            bonuses.append(0.1)
    # Price influences how HARD the engine cools (via the setpoint), never WHETHER it
    # cools. Subtracting it here meant an expensive evening pushed the cool-start point
    # from 25 C out to 28 C -- the room got hot to save money nobody agreed to spend.
    confidence = confidence_score(base, None, bonuses)
    reason = pressure_tier(confidence, "thermal")
    return ThermalResult(base, confidence, reason)

from __future__ import annotations
from dataclasses import dataclass
from .const import STRATEGY_DEHUMIDIFY
@dataclass(slots=True)
class LearningState:
    drying_successes: int = 0
    drying_failures: int = 0


class AdaptiveLearning:
    """Tracks whether dehumidifying actually dries the room.

    Cooling is NOT tracked here. A raw before/after temperature comparison is confounded --
    it credits the AC when the sun sets and blames it when the outdoors heats up -- and it
    used to count fan circulation as a failed cooling attempt, which biased the engine
    against ever cooling. `ThermalModel` measures cooling properly, with the outdoor, solar
    and internal loads controlled for, so the cooling bias comes from there.
    """
    def __init__(self) -> None:
        self.state = LearningState()
    def update(self, previous_snapshot, previous_decision, snapshot) -> None:
        if previous_snapshot is None or previous_decision is None:
            return
        if previous_decision.strategy == STRATEGY_DEHUMIDIFY and snapshot.humidity is not None and previous_snapshot.humidity is not None:
            if snapshot.humidity < previous_snapshot.humidity - 0.5:
                self.state.drying_successes += 1
            elif snapshot.humidity > previous_snapshot.humidity + 0.5:
                self.state.drying_failures += 1
    @staticmethod
    def _bias(successes: int, failures: int) -> float:
        # Small, bounded nudge (+/-0.05) once there's enough evidence (>=5 samples).
        total = successes + failures
        if total < 5:
            return 0.0
        return max(min((successes - failures) / total * 0.05, 0.05), -0.05)
    def drying_bias(self) -> float:
        return self._bias(self.state.drying_successes, self.state.drying_failures)
    def reset(self) -> None:
        self.state = LearningState()

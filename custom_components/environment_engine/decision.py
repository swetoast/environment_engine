from __future__ import annotations
from dataclasses import dataclass
from .const import ACTION_NONE
@dataclass(slots=True)
class Decision:
    strategy: str
    hvac_mode: str | None
    target_temperature: int | None
    fan_action: str
    fan_speed: str | None
    cover_action: str
    purifier_action: str
    confidence: float
    reason: str
    blocked: bool = False
    humidifier_action: str = ACTION_NONE
    humidifier_target: int | None = None
    purifier_speed: str | None = None
    ionizer_action: str = ACTION_NONE
    ventilation_action: str = ACTION_NONE
    climate_fan_speed: str | None = None
    def signature(self) -> tuple:
        return (self.strategy, self.hvac_mode, self.target_temperature, self.fan_action, self.fan_speed, self.cover_action, self.purifier_action, self.humidifier_action, self.humidifier_target, self.purifier_speed, self.ionizer_action, self.ventilation_action, self.climate_fan_speed)

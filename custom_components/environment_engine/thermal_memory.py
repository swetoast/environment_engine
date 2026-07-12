from __future__ import annotations
from dataclasses import dataclass
@dataclass(slots=True)
class ThermalMemory:
    previous_indoor: float | None = None
    previous_humidity: float | None = None
    thermal_inertia: float = 0.0
    temperature_trend: float = 0.0
    humidity_trend: float = 0.0
class ThermalMemoryEngine:
    def __init__(self) -> None:
        self.memory = ThermalMemory()
    def update(self, indoor: float, humidity: float | None, outdoor: float | None) -> ThermalMemory:
        if self.memory.previous_indoor is not None:
            self.memory.temperature_trend = indoor - self.memory.previous_indoor
        if humidity is not None and self.memory.previous_humidity is not None:
            self.memory.humidity_trend = humidity - self.memory.previous_humidity
        if outdoor is not None:
            self.memory.thermal_inertia = min(abs(indoor - outdoor) / 10.0, 1.0)
        self.memory.previous_indoor = indoor
        self.memory.previous_humidity = humidity
        return self.memory

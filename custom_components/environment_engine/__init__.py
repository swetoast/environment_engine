from __future__ import annotations
from .air_quality import AirQualityResult, evaluate_air_quality
from .energy import EnergyResult, evaluate_energy
from .humidity import HumidityResult, evaluate_humidity
from .mold import MoldResult, evaluate_mold
from .safety import SafetyResult, evaluate_safety
from .solar import SolarResult, evaluate_solar
from .thermal import ThermalResult, evaluate_thermal


def drying_pressure(ev) -> float:
    """Combined humidity + mold pressure that drives dry mode / a dehumidifier."""
    return max(ev["humidity"].confidence, ev["mold"].risk)

__all__ = ["AirQualityResult", "EnergyResult", "HumidityResult", "MoldResult", "SafetyResult", "SolarResult", "ThermalResult", "evaluate_air_quality", "evaluate_energy", "evaluate_humidity", "evaluate_mold", "evaluate_safety", "evaluate_solar", "evaluate_thermal", "drying_pressure"]

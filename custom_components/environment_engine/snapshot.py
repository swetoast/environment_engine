from __future__ import annotations
from dataclasses import dataclass, field
@dataclass(slots=True)
class Snapshot:
    indoor_temp: float
    humidity: float | None
    outdoor_temp: float | None
    occupancy: bool
    window_open: bool
    energy_price: float | None
    co2: float | None
    voc: float | None
    hvac_mode: str
    hvac_modes: list[str] = field(default_factory=list)
    min_temp: float | None = None
    max_temp: float | None = None
    temperature_unit: str = "°C"
    sun_up: bool = False
    sun_elevation: float | None = None
    smoke_detected: bool = False
    outlet_overloaded: bool = False
    temperature_valid: bool = True
    climate_valid: bool = True
    feels_like: float | None = None
    portable_ac: bool = False
    vented: bool = False
    quiet: bool = False
    cover_closed: bool = False
    lux: float | None = None
    humidifier_class: str | None = None
    aqi: float | None = None
    aqi_dominant_factor: str | None = None
    outdoor_aqi: float | None = None
    lightning_hold: bool = False
    lightning_closest: float | None = None
    lightning_strikes: int = 0
    lightning_band: str = "clear"
    pm25: float | None = None
    pm10: float | None = None
    dark: bool = False
    forecast_high: float | None = None
    forecast_pressure: float = 0.0
    price_average: float | None = None
    price_rank: float | None = None
    price_precool: bool = False
    invalid_entities: list[str] = field(default_factory=list)

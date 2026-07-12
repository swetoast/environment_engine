from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .const import CONF_BLINDS, CONF_CLIMATE, CONF_CO2, CONF_FAN, CONF_LUX, CONF_AQI, CONF_HUMIDIFIER, CONF_OUTDOOR_AQI, CONF_PM10, CONF_PM25, CONF_VENTILATION, CONF_HUMIDITY, CONF_LIGHTNING_DISTANCE, CONF_OCCUPANCY, CONF_OUTLET_OVERLOAD, CONF_PRICE, CONF_PURIFIER, CONF_IONIZER, CONF_SMOKE, CONF_TEMPERATURE, CONF_VOC, CONF_WEATHER, CONF_WINDOW
@dataclass(slots=True)
class Capabilities:
    climate: bool
    temperature: bool
    humidity: bool
    weather: bool
    occupancy: bool
    windows: bool
    pricing: bool
    air_quality: bool
    blinds: bool
    illuminance: bool
    fan: bool
    purifier: bool
    humidifier: bool
    ionizer: bool
    ventilation: bool
    smoke: bool
    lightning: bool
    outlet_overload: bool
def build_capabilities(config: dict[str, Any]) -> Capabilities:
    return Capabilities(
        climate=bool(config.get(CONF_CLIMATE)),
        temperature=bool(config.get(CONF_TEMPERATURE)),
        humidity=bool(config.get(CONF_HUMIDITY)),
        weather=bool(config.get(CONF_WEATHER)),
        occupancy=bool(config.get(CONF_OCCUPANCY)),
        windows=bool(config.get(CONF_WINDOW)),
        pricing=bool(config.get(CONF_PRICE)),
        air_quality=bool(config.get(CONF_CO2) or config.get(CONF_VOC) or config.get(CONF_AQI) or config.get(CONF_OUTDOOR_AQI) or config.get(CONF_PM25) or config.get(CONF_PM10)),
        blinds=bool(config.get(CONF_BLINDS)),
        illuminance=bool(config.get(CONF_LUX)),
        fan=bool(config.get(CONF_FAN)),
        purifier=bool(config.get(CONF_PURIFIER)),
        humidifier=bool(config.get(CONF_HUMIDIFIER)),
        ionizer=bool(config.get(CONF_IONIZER)),
        ventilation=bool(config.get(CONF_VENTILATION)),
        smoke=bool(config.get(CONF_SMOKE)),
        lightning=bool(config.get(CONF_LIGHTNING_DISTANCE)),
        outlet_overload=bool(config.get(CONF_OUTLET_OVERLOAD)),
    )

from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .const import DEFAULTS, IONIZER_NEVER, IONIZER_SURGE, IONIZER_WITH_PURIFIER, PRICING_FIXED, PRICING_SPOT, OPT_AIR_RECOVERY, OPT_AQI_THRESHOLD, OPT_FILTER_LIFE, OPT_PORTABLE_AC, OPT_PRICING_MODE, OPT_VENT_REVERT, OPT_PRESENCE_HOLD, OPT_CO2_THRESHOLD, OPT_LUX_THRESHOLD, OPT_PRICE_HIGH, OPT_HUMIDITY_COMFORT, OPT_CO2_VENTILATE, OPT_COMPRESSOR_MIN_CYCLE, OPT_DEVICE_MIN_CYCLE, OPT_QUIET_HOURS, OPT_QUIET_START, OPT_QUIET_END, OPT_QUIET_MAX_TEMP, OPT_IONIZER_MODE, OPT_DEWPOINT_MARGIN, OPT_LIGHTNING_DISTANCE, OPT_FAN_COMFORT, OPT_OUTDOOR_AQI_THRESHOLD, OPT_PM10_THRESHOLD, OPT_PM25_THRESHOLD, OPT_SLEEP_LUX, OPT_HUMIDITY_COOLING, OPT_TARGET_HUMIDITY, OPT_TARGET_TEMPERATURE, OPT_VOC_THRESHOLD
@dataclass(slots=True)
class EngineOptions:
    auto_apply: bool = False
    update_interval: int = 60
    min_change_interval: int = 180
    target_temperature: int = 22
    co2_threshold: int = 900
    voc_threshold: int = 250
    price_high: float = 1.5
    lux_threshold: int = 1000
    target_humidity: int = 50
    aqi_threshold: int = 70
    humidity_comfort: int = 60
    humidity_cooling: float = 1.0
    fan_comfort: bool = True
    compressor_min_cycle: int = 300
    outdoor_aqi_threshold: int = 100
    dewpoint_margin: float = 2.0
    co2_ventilate: int = 1000
    sleep_lux: int = 5
    pm25_threshold: int = 50
    pm10_threshold: int = 100
    lightning_distance: int = 30
    air_recovery: int = 10
    presence_hold: int = 5
    filter_life: int = 0
    portable_ac: bool = False
    vent_revert: int = 8
    pricing_mode: str = "spot"
    device_min_cycle: int = 120
    quiet_hours: bool = False
    quiet_start: str = "22:00"
    quiet_end: str = "07:00"
    quiet_max_temp: float = 26.0
    ionizer_mode: str = "with_purifier"
    @property
    def target(self) -> int:
        # One comfort baseline. The engine derives eco/sleep/away behaviour itself
        # via the target resolver, so there are no separate modes to pick.
        return self.target_temperature
def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
def _time_str(value, default: str) -> str:
    """Normalise a TimeSelector value (time / 'HH:MM[:SS]' / dict) to 'HH:MM'.
    Keeps stored options robust regardless of which shape HA handed us."""
    from .quiet_hours import parse_time
    parsed = parse_time(value)
    return parsed.strftime("%H:%M") if parsed is not None else default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
def build_options(data: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULTS, **data, **options}
def resolved_options(data: dict[str, Any], options: dict[str, Any]) -> EngineOptions:
    merged = build_options(data, options)
    return EngineOptions(
        auto_apply=bool(merged.get("auto_apply", DEFAULTS["auto_apply"])),
        update_interval=max(_as_int(merged.get("update_interval"), DEFAULTS["update_interval"]), 15),
        min_change_interval=max(_as_int(merged.get("min_change_interval"), DEFAULTS["min_change_interval"]), 0),
        target_temperature=min(max(_as_int(merged.get(OPT_TARGET_TEMPERATURE), DEFAULTS[OPT_TARGET_TEMPERATURE]), 16), 30),
        co2_threshold=max(_as_int(merged.get(OPT_CO2_THRESHOLD), DEFAULTS[OPT_CO2_THRESHOLD]), 1),
        voc_threshold=max(_as_int(merged.get(OPT_VOC_THRESHOLD), DEFAULTS[OPT_VOC_THRESHOLD]), 1),
        price_high=max(_as_float(merged.get(OPT_PRICE_HIGH), DEFAULTS[OPT_PRICE_HIGH]), 0.01),
        lux_threshold=max(_as_int(merged.get(OPT_LUX_THRESHOLD), DEFAULTS[OPT_LUX_THRESHOLD]), 1),
        target_humidity=min(max(_as_int(merged.get(OPT_TARGET_HUMIDITY), DEFAULTS[OPT_TARGET_HUMIDITY]), 20), 80),
        aqi_threshold=max(_as_int(merged.get(OPT_AQI_THRESHOLD), DEFAULTS[OPT_AQI_THRESHOLD]), 1),
        humidity_comfort=min(max(_as_int(merged.get(OPT_HUMIDITY_COMFORT), DEFAULTS[OPT_HUMIDITY_COMFORT]), 30), 90),
        humidity_cooling=min(max(_as_float(merged.get(OPT_HUMIDITY_COOLING), DEFAULTS[OPT_HUMIDITY_COOLING]), 0.0), 3.0),
        fan_comfort=bool(merged.get(OPT_FAN_COMFORT, DEFAULTS[OPT_FAN_COMFORT])),
        compressor_min_cycle=max(_as_int(merged.get(OPT_COMPRESSOR_MIN_CYCLE), DEFAULTS[OPT_COMPRESSOR_MIN_CYCLE]), 0),
        outdoor_aqi_threshold=max(_as_int(merged.get(OPT_OUTDOOR_AQI_THRESHOLD), DEFAULTS[OPT_OUTDOOR_AQI_THRESHOLD]), 1),
        dewpoint_margin=min(max(_as_float(merged.get(OPT_DEWPOINT_MARGIN), DEFAULTS[OPT_DEWPOINT_MARGIN]), 0.0), 6.0),
        lightning_distance=max(_as_int(merged.get(OPT_LIGHTNING_DISTANCE), DEFAULTS[OPT_LIGHTNING_DISTANCE]), 1),
        air_recovery=max(_as_int(merged.get(OPT_AIR_RECOVERY), DEFAULTS[OPT_AIR_RECOVERY]), 0),
        presence_hold=max(_as_int(merged.get(OPT_PRESENCE_HOLD), DEFAULTS[OPT_PRESENCE_HOLD]), 0),
        filter_life=max(_as_int(merged.get(OPT_FILTER_LIFE), DEFAULTS[OPT_FILTER_LIFE]), 0),
        portable_ac=bool(merged.get(OPT_PORTABLE_AC, DEFAULTS[OPT_PORTABLE_AC])),
        vent_revert=max(_as_int(merged.get(OPT_VENT_REVERT), DEFAULTS[OPT_VENT_REVERT]), 0),
        pricing_mode=(merged.get(OPT_PRICING_MODE) if merged.get(OPT_PRICING_MODE) in (PRICING_SPOT, PRICING_FIXED) else DEFAULTS[OPT_PRICING_MODE]),
        device_min_cycle=max(_as_int(merged.get(OPT_DEVICE_MIN_CYCLE), DEFAULTS[OPT_DEVICE_MIN_CYCLE]), 0),
        quiet_hours=bool(merged.get(OPT_QUIET_HOURS, DEFAULTS[OPT_QUIET_HOURS])),
        quiet_start=_time_str(merged.get(OPT_QUIET_START), DEFAULTS[OPT_QUIET_START]),
        quiet_end=_time_str(merged.get(OPT_QUIET_END), DEFAULTS[OPT_QUIET_END]),
        quiet_max_temp=_as_float(merged.get(OPT_QUIET_MAX_TEMP), DEFAULTS[OPT_QUIET_MAX_TEMP]),
        ionizer_mode=(merged.get(OPT_IONIZER_MODE) if merged.get(OPT_IONIZER_MODE) in (IONIZER_WITH_PURIFIER, IONIZER_SURGE, IONIZER_NEVER) else DEFAULTS[OPT_IONIZER_MODE]),
        co2_ventilate=max(_as_int(merged.get(OPT_CO2_VENTILATE), DEFAULTS[OPT_CO2_VENTILATE]), 400),
        sleep_lux=max(_as_int(merged.get(OPT_SLEEP_LUX), DEFAULTS[OPT_SLEEP_LUX]), 0),
        pm25_threshold=max(_as_int(merged.get(OPT_PM25_THRESHOLD), DEFAULTS[OPT_PM25_THRESHOLD]), 1),
        pm10_threshold=max(_as_int(merged.get(OPT_PM10_THRESHOLD), DEFAULTS[OPT_PM10_THRESHOLD]), 1),
    )

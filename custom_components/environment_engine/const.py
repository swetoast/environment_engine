from __future__ import annotations
from homeassistant.const import Platform
DOMAIN = "environment_engine"
CONF_ENTRY_TYPE = "entry_type"
ENTRY_GLOBAL = "global"
ENTRY_ROOM = "room"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.BUTTON]
MANUFACTURER = "swetoast"
CONF_NAME = "name"
CONF_CLIMATE = "climate_entity"
CONF_TEMPERATURE = "temperature_sensor"
CONF_HUMIDITY = "humidity_sensor"
CONF_WEATHER = "weather_entity"
CONF_OCCUPANCY = "occupancy_entity"
CONF_WINDOW = "window_entity"
CONF_VENT = "vent_entity"
CONF_PRICE = "price_entity"
CONF_CO2 = "co2_sensor"
CONF_VOC = "voc_sensor"
CONF_LUX = "lux_sensor"
CONF_HUMIDIFIER = "humidifier_entity"
CONF_AQI = "aqi_sensor"
CONF_IONIZER = "ionizer_entity"
CONF_FORECAST_HIGH = "forecast_high_sensor"
CONF_PRICE_AVERAGE = "price_average_sensor"
CONF_PRICE_FORECAST = "price_forecast_sensor"
CONF_OUTDOOR_AQI = "outdoor_aqi_sensor"
CONF_LIGHTNING_DISTANCE = "lightning_distance_sensor"
CONF_PM25 = "pm25_sensor"
CONF_PM10 = "pm10_sensor"
CONF_VENTILATION = "ventilation_entity"
CONF_BLINDS = "blinds_cover"
CONF_FAN = "fan_entity"
CONF_PURIFIER = "purifier_entity"
CONF_SMOKE = "smoke_sensor"
CONF_OUTLET_OVERLOAD = "outlet_overload_sensor"
OPT_TARGET_TEMPERATURE = "target_temperature"
OPT_AUTO_APPLY = "auto_apply"
OPT_UPDATE_INTERVAL = "update_interval"
OPT_MIN_CHANGE_INTERVAL = "min_change_interval"
OPT_CO2_THRESHOLD = "co2_threshold"
OPT_VOC_THRESHOLD = "voc_threshold"
OPT_PRICE_HIGH = "price_high"
OPT_PRICING_MODE = "pricing_mode"
OPT_LUX_THRESHOLD = "lux_threshold"
OPT_TARGET_HUMIDITY = "target_humidity"
OPT_AQI_THRESHOLD = "aqi_threshold"
OPT_HUMIDITY_COMFORT = "humidity_comfort"
OPT_HUMIDITY_COOLING = "humidity_cooling"
OPT_FAN_COMFORT = "fan_comfort"
OPT_COMPRESSOR_MIN_CYCLE = "compressor_min_cycle"
OPT_DEVICE_MIN_CYCLE = "device_min_cycle"
OPT_QUIET_HOURS = "quiet_hours"
OPT_QUIET_START = "quiet_start"
OPT_QUIET_END = "quiet_end"
OPT_QUIET_MAX_TEMP = "quiet_max_temp"
OPT_IONIZER_MODE = "ionizer_mode"
OPT_OUTDOOR_AQI_THRESHOLD = "outdoor_aqi_threshold"
OPT_DEWPOINT_MARGIN = "dewpoint_margin"
OPT_LIGHTNING_DISTANCE = "lightning_distance"
OPT_CO2_VENTILATE = "co2_ventilate"
OPT_SLEEP_LUX = "sleep_lux"
OPT_AIR_RECOVERY = "air_recovery"
OPT_PRESENCE_HOLD = "presence_hold"
OPT_FILTER_LIFE = "filter_life"
OPT_PORTABLE_AC = "portable_ac"
OPT_VENT_REVERT = "vent_revert"
OPT_PM25_THRESHOLD = "pm25_threshold"
OPT_PM10_THRESHOLD = "pm10_threshold"
STRATEGY_AIR_QUALITY = "air_quality"
STRATEGY_SOLAR_MITIGATION = "solar_mitigation"
STRATEGY_HUMIDIFY = "humidify"
STRATEGY_AIR_CIRCULATION = "air_circulation"
STRATEGY_QUIET_COOLING = "quiet_cooling"
STRATEGY_AWAY_IDLE = "away_idle"
IONIZER_WITH_PURIFIER = "with_purifier"
IONIZER_SURGE = "surge"
IONIZER_NEVER = "never"
PRICING_SPOT = "spot"
PRICING_FIXED = "fixed"
STRATEGY_COOLING = "cooling"
STRATEGY_DEHUMIDIFY = "dehumidify"
STRATEGY_IDLE = "idle"
STRATEGY_MOLD_PREVENTION = "mold_prevention"
STRATEGY_PASSIVE_VENTILATION = "passive_ventilation"
STRATEGY_SAFETY_STOP = "safety_stop"
STRATEGY_CLIMATE_OFFLINE = "climate_offline"
STRATEGY_FRESH_AIR = "fresh_air"
ACTION_NONE = "none"
ACTION_ON = "on"
ACTION_OFF = "off"
ACTION_OPEN = "open"
ACTION_CLOSE = "close"
HVAC_COOL = "cool"
HVAC_DRY = "dry"
HVAC_FAN_ONLY = "fan_only"
HVAC_OFF = "off"
DEFAULTS = {
    OPT_TARGET_TEMPERATURE: 22,
    OPT_AUTO_APPLY: False,
    OPT_UPDATE_INTERVAL: 60,
    OPT_MIN_CHANGE_INTERVAL: 180,
    OPT_CO2_THRESHOLD: 900,
    OPT_VOC_THRESHOLD: 250,
    OPT_PRICE_HIGH: 1.5,
    OPT_PRICING_MODE: PRICING_SPOT,
    OPT_LUX_THRESHOLD: 1000,
    OPT_TARGET_HUMIDITY: 50,
    OPT_AQI_THRESHOLD: 70,
    OPT_HUMIDITY_COMFORT: 60,
    OPT_HUMIDITY_COOLING: 1.0,
    OPT_FAN_COMFORT: True,
    OPT_COMPRESSOR_MIN_CYCLE: 300,
    OPT_DEVICE_MIN_CYCLE: 120,
    OPT_QUIET_HOURS: False,
    OPT_QUIET_START: "22:00",
    OPT_QUIET_END: "07:00",
    OPT_QUIET_MAX_TEMP: 26.0,
    OPT_IONIZER_MODE: IONIZER_WITH_PURIFIER,
    OPT_OUTDOOR_AQI_THRESHOLD: 100,
    OPT_DEWPOINT_MARGIN: 2.0,
    OPT_LIGHTNING_DISTANCE: 40,
    OPT_CO2_VENTILATE: 1000,
    OPT_SLEEP_LUX: 5,
    OPT_AIR_RECOVERY: 10,
    OPT_PRESENCE_HOLD: 5,
    OPT_FILTER_LIFE: 0,
    OPT_PORTABLE_AC: False,
    OPT_VENT_REVERT: 8,
    OPT_PM25_THRESHOLD: 50,
    OPT_PM10_THRESHOLD: 100,
}

# Every optional entity slot, in form order. Single source of truth for the
# config flow (which slots exist / count) and the coordinator (availability scan).

# Shared across the whole home -- configured once on the Global entry.
GLOBAL_ENTITY_KEYS = (
    CONF_WEATHER, CONF_FORECAST_HIGH, CONF_OUTDOOR_AQI, CONF_LIGHTNING_DISTANCE, CONF_PRICE, CONF_PRICE_AVERAGE, CONF_PRICE_FORECAST,
)
# Specific to one room/zone -- configured per Room entry.
ROOM_ENTITY_KEYS = (
    CONF_CLIMATE, CONF_TEMPERATURE,
    CONF_FAN, CONF_BLINDS, CONF_LUX,
    CONF_AQI, CONF_PM25, CONF_PM10, CONF_PURIFIER, CONF_IONIZER, CONF_VENTILATION, CONF_CO2, CONF_VOC,
    CONF_HUMIDITY, CONF_HUMIDIFIER,
    CONF_OCCUPANCY, CONF_WINDOW, CONF_VENT,
    CONF_SMOKE, CONF_OUTLET_OVERLOAD,
)
# Everything, for the coordinator's availability scan.
ENTITY_KEYS = GLOBAL_ENTITY_KEYS + ROOM_ENTITY_KEYS

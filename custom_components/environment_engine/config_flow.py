from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from .const import (
    IONIZER_NEVER, IONIZER_SURGE, IONIZER_WITH_PURIFIER, PRICING_FIXED, PRICING_SPOT,
    CONF_AQI, CONF_BLINDS, CONF_CLIMATE, CONF_CO2, CONF_ENTRY_TYPE, CONF_FAN, CONF_FORECAST_HIGH,
    CONF_HUMIDIFIER, CONF_HUMIDITY, CONF_IONIZER, CONF_LUX, CONF_NAME,
    CONF_LIGHTNING_DISTANCE, CONF_OCCUPANCY, CONF_OUTDOOR_AQI, CONF_OUTLET_OVERLOAD, CONF_PM10, CONF_PM25,
    CONF_PRICE, CONF_PRICE_AVERAGE, CONF_PRICE_FORECAST, CONF_PURIFIER, CONF_SMOKE, CONF_TEMPERATURE, CONF_VENTILATION,
    CONF_VOC, CONF_WEATHER, CONF_WINDOW, CONF_VENT,
    DEFAULTS, DOMAIN, ENTRY_GLOBAL, ENTRY_ROOM, ROOM_ENTITY_KEYS,
    OPT_AIR_RECOVERY, OPT_AQI_THRESHOLD, OPT_AUTO_APPLY, OPT_FILTER_LIFE, OPT_PORTABLE_AC, OPT_VENT_REVERT, OPT_CO2_THRESHOLD, OPT_CO2_VENTILATE, OPT_COMPRESSOR_MIN_CYCLE, OPT_DEVICE_MIN_CYCLE, OPT_QUIET_HOURS, OPT_QUIET_START, OPT_QUIET_END, OPT_QUIET_MAX_TEMP, OPT_IONIZER_MODE,
    OPT_DEWPOINT_MARGIN, OPT_FAN_COMFORT, OPT_HUMIDITY_COMFORT, OPT_HUMIDITY_COOLING, OPT_LUX_THRESHOLD,
    OPT_LIGHTNING_DISTANCE, OPT_MIN_CHANGE_INTERVAL, OPT_OUTDOOR_AQI_THRESHOLD, OPT_PM10_THRESHOLD, OPT_PM25_THRESHOLD, OPT_PRESENCE_HOLD,
    OPT_PRICE_HIGH, OPT_PRICING_MODE, OPT_SLEEP_LUX, OPT_TARGET_HUMIDITY, OPT_TARGET_TEMPERATURE, OPT_UPDATE_INTERVAL,
    OPT_VOC_THRESHOLD,
)
from .discovery import discover_area
from .options import build_options

CONF_AREA = "area"

# One source of truth: key -> (domain, device_class|None).
_ENTITY_SPEC = {
    CONF_WEATHER: ("weather", None),
    CONF_FORECAST_HIGH: (["weather", "sensor"], None),
    CONF_OUTDOOR_AQI: ("sensor", None),
    CONF_LIGHTNING_DISTANCE: ("sensor", None),
    CONF_PRICE: ("sensor", None),
    CONF_PRICE_AVERAGE: ("sensor", None),
    CONF_PRICE_FORECAST: ("sensor", None),
    CONF_CLIMATE: ("climate", None),
    CONF_TEMPERATURE: ("sensor", "temperature"),
    CONF_FAN: ("fan", None),
    CONF_BLINDS: ("cover", None),
    CONF_LUX: ("sensor", "illuminance"),
    CONF_AQI: ("sensor", "aqi"),
    CONF_PM25: ("sensor", ["pm1", "pm25"]),
    CONF_PM10: ("sensor", "pm10"),
    CONF_PURIFIER: (["fan", "switch"], None),
    CONF_IONIZER: ("switch", None),
    CONF_VENTILATION: (["fan", "switch", "cover"], None),
    CONF_CO2: ("sensor", "carbon_dioxide"),
    CONF_VOC: ("sensor", None),
    CONF_HUMIDITY: ("sensor", "humidity"),
    CONF_HUMIDIFIER: ("humidifier", None),
    CONF_OCCUPANCY: (["person", "device_tracker", "binary_sensor"], None),
    CONF_WINDOW: ("binary_sensor", None),
    CONF_VENT: ("binary_sensor", None),
    CONF_SMOKE: ("binary_sensor", "smoke"),
    CONF_OUTLET_OVERLOAD: ("binary_sensor", None),
}
# Global entry: one flat form.
_GLOBAL_FIELDS = (CONF_WEATHER, CONF_FORECAST_HIGH, CONF_OUTDOOR_AQI, CONF_LIGHTNING_DISTANCE, CONF_PRICE, CONF_PRICE_AVERAGE, CONF_PRICE_FORECAST)
# Room entry: grouped into collapsible sections (section_key -> field keys).
_ROOM_SECTIONS = (
    ("climate_comfort", (CONF_CLIMATE, CONF_TEMPERATURE, CONF_FAN, CONF_BLINDS, CONF_LUX)),
    ("air_quality", (CONF_AQI, CONF_PM25, CONF_PM10, CONF_PURIFIER, CONF_IONIZER, CONF_VENTILATION, CONF_CO2, CONF_VOC)),
    ("humidity", (CONF_HUMIDITY, CONF_HUMIDIFIER)),
    ("presence_safety", (CONF_OCCUPANCY, CONF_WINDOW, CONF_VENT, CONF_SMOKE, CONF_OUTLET_OVERLOAD)),
)
_GLOBAL_NUMBER_OPTIONS = (
    (OPT_PRICE_HIGH, dict(min=0.1, max=100, step=0.1)),
    (OPT_OUTDOOR_AQI_THRESHOLD, dict(min=10, max=500, step=5, unit_of_measurement="AQI")),
    (OPT_LIGHTNING_DISTANCE, dict(min=1, max=100, step=1, unit_of_measurement="km")),
)
_ROOM_NUMBER_OPTIONS = (
    (OPT_TARGET_TEMPERATURE, dict(min=16, max=30, step=1, unit_of_measurement="°C")),
    (OPT_UPDATE_INTERVAL, dict(min=15, max=600, step=15, unit_of_measurement="s")),
    (OPT_MIN_CHANGE_INTERVAL, dict(min=0, max=1800, step=30, unit_of_measurement="s")),
    (OPT_COMPRESSOR_MIN_CYCLE, dict(min=0, max=1800, step=30, unit_of_measurement="s")),
    (OPT_DEVICE_MIN_CYCLE, dict(min=0, max=900, step=30, unit_of_measurement="s")),
    (OPT_QUIET_MAX_TEMP, dict(min=18, max=32, step=0.5, unit_of_measurement="°C")),
    (OPT_CO2_THRESHOLD, dict(min=400, max=2000, step=50, unit_of_measurement="ppm")),
    (OPT_CO2_VENTILATE, dict(min=600, max=2500, step=50, unit_of_measurement="ppm")),
    (OPT_VOC_THRESHOLD, dict(min=10, max=2000, step=10)),
    (OPT_LUX_THRESHOLD, dict(min=100, max=20000, step=100, unit_of_measurement="lx")),
    (OPT_SLEEP_LUX, dict(min=0, max=50, step=1, unit_of_measurement="lx")),
    (OPT_TARGET_HUMIDITY, dict(min=20, max=80, step=1, unit_of_measurement="%")),
    (OPT_HUMIDITY_COMFORT, dict(min=30, max=90, step=1, unit_of_measurement="%")),
    (OPT_HUMIDITY_COOLING, dict(min=0, max=3, step=0.5, unit_of_measurement="°C")),
    (OPT_AQI_THRESHOLD, dict(min=10, max=300, step=5, unit_of_measurement="AQI")),
    (OPT_AIR_RECOVERY, dict(min=0, max=60, step=1, unit_of_measurement="min")),
    (OPT_PRESENCE_HOLD, dict(min=0, max=60, step=1, unit_of_measurement="min")),
    (OPT_FILTER_LIFE, dict(min=0, max=5000, step=50, unit_of_measurement="h")),
    (OPT_VENT_REVERT, dict(min=0, max=24, step=1, unit_of_measurement="h")),
    (OPT_PM25_THRESHOLD, dict(min=5, max=250, step=5, unit_of_measurement="µg/m³")),
    (OPT_PM10_THRESHOLD, dict(min=10, max=400, step=5, unit_of_measurement="µg/m³")),
    (OPT_DEWPOINT_MARGIN, dict(min=0, max=6, step=0.5, unit_of_measurement="°C")),
)


def _entity_selector(key):
    domain, device_class = _ENTITY_SPEC[key]
    cfg = {"multiple": True, "domain": domain}
    if device_class:
        cfg["device_class"] = device_class
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


def _field(key, defaults):
    return vol.Optional(key, description={"suggested_value": defaults.get(key)}), _entity_selector(key)


def _number_field(key, defaults, **cfg):
    field = vol.Required(key, default=defaults.get(key, DEFAULTS[key]))
    return field, selector.NumberSelector(selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, **cfg))


def _flatten(user_input: dict) -> dict:
    """Merge section sub-dicts up to a flat mapping (sections nest their fields)."""
    flat = {}
    for key, value in user_input.items():
        if isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


def _clean(user_input: dict) -> dict:
    return {key: value for key, value in _flatten(user_input).items() if value not in (None, "", [])}


def _global_schema(defaults: dict):
    fields = {}
    for key in _GLOBAL_FIELDS:
        f, sel = _field(key, defaults)
        fields[f] = sel
    return vol.Schema(fields)


def _room_schema(defaults: dict):
    fields = {vol.Optional(CONF_NAME, description={"suggested_value": defaults.get(CONF_NAME)}): selector.TextSelector()}
    for section_key, keys in _ROOM_SECTIONS:
        inner = {}
        for key in keys:
            f, sel = _field(key, defaults)
            inner[f] = sel
        fields[vol.Required(section_key)] = section(vol.Schema(inner), {"collapsed": section_key != "climate_comfort"})
    return vol.Schema(fields)


def _options_schema(number_spec, defaults: dict, booleans=(), selects=(), times=()):
    fields = {}
    for key in booleans:
        fields[vol.Required(key, default=defaults.get(key, DEFAULTS[key]))] = selector.BooleanSelector()
    for key, choices in selects:
        fields[vol.Required(key, default=defaults.get(key, DEFAULTS[key]))] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=list(choices), translation_key=key, mode=selector.SelectSelectorMode.DROPDOWN))
    for key in times:
        fields[vol.Required(key, default=defaults.get(key, DEFAULTS[key]))] = selector.TimeSelector()
    for key, cfg in number_spec:
        field, sel = _number_field(key, defaults, **cfg)
        fields[field] = sel
    return vol.Schema(fields)


def _has_any(data: dict, keys) -> bool:
    return any(data.get(key) for key in keys)


class EnvironmentEngineConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self) -> None:
        self._discovered: dict = {}

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["global", "room"])

    async def async_step_global(self, user_input=None):
        for entry in self._async_current_entries():
            if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_GLOBAL:
                return self.async_abort(reason="single_global")
        if user_input is not None:
            data = _clean(user_input)
            data[CONF_ENTRY_TYPE] = ENTRY_GLOBAL
            return self.async_create_entry(title="Global", data=data)
        return self.async_show_form(step_id="global", data_schema=_global_schema({}))

    async def async_step_room(self, user_input=None):
        if user_input is not None:
            area_id = user_input.get(CONF_AREA)
            discovered = discover_area(self.hass, area_id) if area_id else {}
            self._discovered = {k: v for k, v in discovered.items() if k in ROOM_ENTITY_KEYS or k == CONF_NAME}
            return await self.async_step_entities()
        return self.async_show_form(step_id="room", data_schema=vol.Schema({vol.Optional(CONF_AREA): selector.AreaSelector()}))

    async def async_step_entities(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not _has_any(cleaned, ROOM_ENTITY_KEYS):
                errors["base"] = "no_entities"
            else:
                cleaned[CONF_ENTRY_TYPE] = ENTRY_ROOM
                return self.async_create_entry(title=cleaned.get(CONF_NAME) or "Room", data=cleaned)
            defaults = _flatten(user_input)
        else:
            defaults = self._discovered
        return self.async_show_form(step_id="entities", data_schema=_room_schema(defaults), errors=errors)

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        is_global = entry.data.get(CONF_ENTRY_TYPE) == ENTRY_GLOBAL
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            cleaned[CONF_ENTRY_TYPE] = entry.data.get(CONF_ENTRY_TYPE)
            if not is_global and not _has_any(cleaned, ROOM_ENTITY_KEYS):
                errors["base"] = "no_entities"
            else:
                return self.async_update_reload_and_abort(entry, data=cleaned, title=cleaned.get(CONF_NAME) or entry.title)
        current = build_options(entry.data, entry.options)
        schema = _global_schema(current) if is_global else _room_schema(current)
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return EnvironmentEngineOptionsFlow()


class EnvironmentEngineOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})
        current = build_options(self.config_entry.data, self.config_entry.options)
        if self.config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_GLOBAL:
            schema = _options_schema(_GLOBAL_NUMBER_OPTIONS, current, selects=((OPT_PRICING_MODE, (PRICING_SPOT, PRICING_FIXED)),))
        else:
            schema = _options_schema(_ROOM_NUMBER_OPTIONS, current, booleans=(OPT_AUTO_APPLY, OPT_FAN_COMFORT, OPT_PORTABLE_AC, OPT_QUIET_HOURS), times=(OPT_QUIET_START, OPT_QUIET_END), selects=((OPT_IONIZER_MODE, (IONIZER_WITH_PURIFIER, IONIZER_SURGE, IONIZER_NEVER)),))
        return self.async_show_form(step_id="init", data_schema=schema)

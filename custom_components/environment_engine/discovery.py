"""Area-based entity discovery for setup.

Given an Area, read HA's entity/device registries to find the entities in that
area and match them to the engine's slots by domain + device_class -- the same
"read what HA already knows" principle as the supported_features work, applied to
onboarding. Matching is pure (and unit-tested); registry access is lazy and
wrapped so a discovery failure simply falls back to the manual form.
"""
from __future__ import annotations
from .const import CONF_AQI, CONF_BLINDS, CONF_CLIMATE, CONF_CO2, CONF_FAN, CONF_FORECAST_HIGH, CONF_HUMIDIFIER, CONF_HUMIDITY, CONF_IONIZER, CONF_LUX, CONF_NAME, CONF_OCCUPANCY, CONF_PURIFIER, CONF_SMOKE, CONF_TEMPERATURE, CONF_VOC, CONF_WINDOW

_VOC_CLASSES = {"volatile_organic_compounds", "volatile_organic_compounds_parts"}


def match_slots(candidates) -> dict:
    """Match (entity_id, domain, device_class, unit, name) tuples to slots.

    Returns every candidate satisfying each slot's predicate (slots are multi-
    entity now), so a room's several fans / sensors are all suggested. Slots not
    tied to an area (weather, price, lightning, outlet) are left for the user.
    """
    items = list(candidates)

    def pick_all(pred):
        return [entity_id for entity_id, domain, device_class, unit, name in items if pred(domain, device_class, unit, entity_id)]

    suggestions: dict[str, list[str]] = {}

    def setif(key, pred):
        values = pick_all(pred)
        if values:
            suggestions[key] = values

    setif(CONF_CLIMATE, lambda d, dc, u, e: d == "climate")
    setif(CONF_TEMPERATURE, lambda d, dc, u, e: d == "sensor" and dc == "temperature")
    setif(CONF_HUMIDITY, lambda d, dc, u, e: d == "sensor" and dc == "humidity")
    setif(CONF_CO2, lambda d, dc, u, e: d == "sensor" and dc == "carbon_dioxide")
    setif(CONF_VOC, lambda d, dc, u, e: d == "sensor" and (dc in _VOC_CLASSES or "voc" in e))
    setif(CONF_LUX, lambda d, dc, u, e: d == "sensor" and (dc == "illuminance" or u == "lx"))
    setif(CONF_AQI, lambda d, dc, u, e: d == "sensor" and (dc == "aqi" or u == "AQI"))
    forecast = pick_all(lambda d, dc, u, e: d == "weather") or pick_all(lambda d, dc, u, e: d == "sensor" and "forecast" in e)
    if forecast:
        suggestions[CONF_FORECAST_HIGH] = forecast
    setif(CONF_WINDOW, lambda d, dc, u, e: d == "binary_sensor" and dc in ("window", "door", "opening"))
    setif(CONF_OCCUPANCY, lambda d, dc, u, e: d == "binary_sensor" and dc in ("occupancy", "presence", "motion"))
    setif(CONF_SMOKE, lambda d, dc, u, e: d == "binary_sensor" and dc == "smoke")
    setif(CONF_BLINDS, lambda d, dc, u, e: d == "cover")
    setif(CONF_PURIFIER, lambda d, dc, u, e: d in ("fan", "switch") and "purif" in e)
    setif(CONF_HUMIDIFIER, lambda d, dc, u, e: d == "humidifier")
    setif(CONF_IONIZER, lambda d, dc, u, e: d == "switch" and "ioniz" in e)
    setif(CONF_FAN, lambda d, dc, u, e: d == "fan" and "purif" not in e)
    return suggestions


def discover_area(hass, area_id: str) -> dict:
    """Build slot suggestions for an area from the registries. Safe to fail."""
    try:
        from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
        entity_ids = {entry.entity_id for entry in er.async_entries_for_area(ent_reg, area_id)}
        for device in dr.async_entries_for_area(dev_reg, area_id):
            for entry in er.async_entries_for_device(ent_reg, device.id):
                if entry.area_id is None:  # inherits the device's area
                    entity_ids.add(entry.entity_id)
        candidates = []
        for entity_id in entity_ids:
            state = hass.states.get(entity_id)
            if state is None:
                continue
            candidates.append((entity_id, entity_id.split(".", 1)[0], state.attributes.get("device_class"), state.attributes.get("unit_of_measurement"), state.attributes.get("friendly_name", "")))
        suggestions = match_slots(candidates)
        area = ar.async_get(hass).async_get_area(area_id)
        if area is not None:
            suggestions.setdefault(CONF_NAME, area.name)
        return suggestions
    except Exception:  # pragma: no cover - never let discovery break setup
        return {}

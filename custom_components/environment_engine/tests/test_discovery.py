"""Area discovery slot-matching (pure; registry access is exercised in HA).

Slots are multi-entity: match_slots returns a LIST of matches per slot so a room
with several fans / sensors gets them all suggested.
"""
from custom_components.environment_engine.const import (
    CONF_BLINDS, CONF_CLIMATE, CONF_CO2, CONF_FAN, CONF_HUMIDITY, CONF_LUX,
    CONF_OCCUPANCY, CONF_PURIFIER, CONF_SMOKE, CONF_TEMPERATURE, CONF_VOC, CONF_WINDOW,
)
from custom_components.environment_engine.discovery import match_slots

TOAST = [
    ("climate.air_conditioner", "climate", None, None, "Air Conditioner"),
    ("sensor.average_indoor_temperature", "sensor", "temperature", "°C", "Indoor Temp"),
    ("sensor.average_indoor_humidity", "sensor", "humidity", "%", "Indoor Humidity"),
    ("sensor.bedroom_carbon_dioxide", "sensor", "carbon_dioxide", "ppm", "CO2"),
    ("sensor.apartment_voc", "sensor", None, "ppb", "Apartment VOC"),
    ("sensor.bedroom_illuminance", "sensor", "illuminance", "lx", "Bedroom Illuminance"),
    ("binary_sensor.main_door", "binary_sensor", "door", None, "Main Door"),
    ("binary_sensor.presence_sensor", "binary_sensor", "occupancy", None, "Presence"),
    ("binary_sensor.smoke_alarm_smoke", "binary_sensor", "smoke", None, "Smoke"),
    ("cover.bedroom_blinds", "cover", "blind", None, "Bedroom Blinds"),
    ("fan.bedroom_fan", "fan", None, None, "Bedroom Fan"),
    ("fan.air_purifier", "fan", None, None, "Air Purifier"),
]


def test_matches_core_slots_as_lists():
    m = match_slots(TOAST)
    assert m[CONF_CLIMATE] == ["climate.air_conditioner"]
    assert "sensor.average_indoor_temperature" in m[CONF_TEMPERATURE]
    assert "sensor.average_indoor_humidity" in m[CONF_HUMIDITY]
    assert "sensor.bedroom_carbon_dioxide" in m[CONF_CO2]
    assert "binary_sensor.smoke_alarm_smoke" in m[CONF_SMOKE]
    assert "cover.bedroom_blinds" in m[CONF_BLINDS]


def test_voc_matched_by_name_when_device_class_missing():
    assert "sensor.apartment_voc" in match_slots(TOAST)[CONF_VOC]


def test_lux_matched_by_unit_or_class():
    assert "sensor.bedroom_illuminance" in match_slots(TOAST)[CONF_LUX]


def test_window_matches_door_class():
    assert "binary_sensor.main_door" in match_slots(TOAST)[CONF_WINDOW]


def test_occupancy_matches_presence():
    assert "binary_sensor.presence_sensor" in match_slots(TOAST)[CONF_OCCUPANCY]


def test_fan_and_purifier_are_disambiguated():
    m = match_slots(TOAST)
    assert m[CONF_FAN] == ["fan.bedroom_fan"]
    assert "fan.air_purifier" in m[CONF_PURIFIER]


def test_multiple_devices_of_same_type_all_matched():
    # the whole point: a room with two fans and two temp sensors suggests all of them
    room = [
        ("fan.bedroom_fan", "fan", None, None, "Bedroom Fan"),
        ("fan.corner_fan", "fan", None, None, "Corner Fan"),
        ("sensor.temp_north", "sensor", "temperature", "°C", "North"),
        ("sensor.temp_south", "sensor", "temperature", "°C", "South"),
    ]
    m = match_slots(room)
    assert set(m[CONF_FAN]) == {"fan.bedroom_fan", "fan.corner_fan"}
    assert set(m[CONF_TEMPERATURE]) == {"sensor.temp_north", "sensor.temp_south"}


def test_empty_area_yields_no_suggestions():
    assert match_slots([]) == {}


def test_unmatched_slots_left_blank():
    m = match_slots(TOAST)
    assert "weather_entity" not in m
    assert "price_entity" not in m

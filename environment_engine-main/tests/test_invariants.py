"""Things that must hold for EVERY home, not just the ones someone thought to write a test for.

`test_random_homes` builds hundreds of random rooms (any mix of devices, Celsius or
Fahrenheit, random options, entities dropping to unavailable) and runs the real engine on
each for several cycles, checking the safety and setpoint invariants after every one.

`test_a_summer_day` runs a physical room model minute by minute through a hot day and checks
the outcome a person would notice: the room is held at the setpoint and the compressor is
not hammered.
"""
import math
import random
from datetime import datetime, timezone

import pytest
from custom_components.environment_engine.thermal_model import ThermalModel
from harness import Clock, Home, State
from test_learning import _trained_thermal

_TAUGHT = _trained_thermal().as_dict()

COMPRESSOR = ("cool", "dry")


def _random_home(rng):
    unit = rng.choice(["°C", "°C", "°C", "°F"])
    dev = (lambda c: round(c * 9 / 5 + 32, 1)) if unit == "°F" else (lambda c: c)
    pick = rng.choice
    states, data = [], {}

    def add(slot, entity_id, state, **attrs):
        states.append(State(entity_id, state, **attrs))
        if slot:
            data.setdefault(slot, []).append(entity_id)

    temp = rng.uniform(14, 36)
    if rng.random() < 0.9:
        modes = pick([["off", "cool", "dry", "fan_only", "heat"], ["off", "cool"], ["off", "cool", "dry"],
                      ["cool", "fan_only"], ["off", "heat", "cool", "fan_only"]])
        attrs = dict(hvac_modes=modes, min_temp=dev(16), max_temp=dev(31), target_temp_step=pick([1, 1, 0.5]),
                     supported_features=pick([385, 1, 0, None]), current_temperature=dev(temp + rng.uniform(-1, 3)))
        if rng.random() < 0.3:
            attrs["hvac_action"] = pick(["cooling", "idle", "off", "drying", "fan"])
        add("climate_entity", "climate.ac", pick([pick(modes)] * 3 + ["unavailable"]), **attrs)
    if rng.random() < 0.9:
        add("temperature_sensor", "sensor.temp", pick([dev(temp), dev(temp), "unavailable", "unknown"]), unit_of_measurement=unit)
    if rng.random() < 0.8:
        add("humidity_sensor", "sensor.humidity", pick([rng.uniform(15, 99), "unavailable"]))
    if rng.random() < 0.7:
        add("fan_entity", "fan.room", pick(["on", "off", "unavailable"]), supported_features=pick([48, 49, 57, None]),
            percentage=pick([0, 33, 66, 100]), percentage_step=pick([33.33, 1, None]))
    if rng.random() < 0.7:
        if "fan_entity" in data and rng.random() < 0.2:
            data["purifier_entity"] = ["fan.room"]                     # the classic misconfiguration
        else:
            entity = pick(["fan.purifier", "switch.purifier"])
            add("purifier_entity", entity, pick(["on", "off", "unavailable"]), supported_features=pick([49, 57, None]),
                percentage=pick([0, 33, 67, 100]), preset_modes=pick([None, ["Auto", "Silent", "Favorite"]]),
                preset_mode=pick([None, "Auto", "Silent"]))
    optional = [
        (0.5, "ionizer_entity", "switch.ionizer", lambda: pick(["on", "off"]), {}),
        (0.5, "aqi_sensor", "sensor.aqi", lambda: rng.uniform(0, 300), {"dominant_factor": pick(["VOC", "PM2.5", None])}),
        (0.5, "pm25_sensor", "sensor.pm25", lambda: rng.uniform(0, 200), {}),
        (0.3, "co2_sensor", "sensor.co2", lambda: rng.uniform(400, 2500), {}),
        (0.4, "outdoor_aqi_sensor", "sensor.outdoor_aqi", lambda: rng.uniform(0, 250), {}),
        (0.3, "outdoor_gas_sensor", "sensor.outdoor_gas", lambda: rng.uniform(0, 1), {}),
        (0.3, "outdoor_pollen_sensor", "sensor.pollen", lambda: rng.uniform(0, 5), {}),
        (0.6, "weather_entity", "weather.home", lambda: "sunny", {"temperature": dev(rng.uniform(-10, 38)), "temperature_unit": unit}),
        (0.5, "occupancy_entity", pick(["binary_sensor.presence", "person.someone", "input_boolean.home"]),
         lambda: pick(["on", "off", "home", "not_home", "unavailable"]), {}),
        (0.4, "window_entity", "binary_sensor.window", lambda: pick(["on", "off"]), {}),
        (0.3, "vent_entity", "binary_sensor.vent", lambda: pick(["on", "off", "unavailable"]), {}),
        (0.3, "smoke_sensor", "binary_sensor.smoke", lambda: pick(["off", "off", "off", "on"]), {}),
        (0.3, "humidifier_entity", "humidifier.unit", lambda: pick(["on", "off"]), {"device_class": pick(["humidifier", "dehumidifier", None])}),
        (0.3, "blinds_cover", "cover.blind", lambda: pick(["open", "closed", "opening"]), {"supported_features": pick([3, 15, 4, None])}),
        (0.3, "ventilation_entity", "fan.erv", lambda: pick(["on", "off"]), {}),
        (0.3, "lux_sensor", "sensor.lux", lambda: rng.uniform(0, 60000), {}),
        (0.3, "price_entity", "sensor.price", lambda: rng.uniform(0, 4), {}),
    ]
    for chance, slot, entity_id, value, attrs in optional:
        if rng.random() < chance:
            add(slot, entity_id, value(), **attrs)
    add(None, "sun.sun", pick(["above_horizon", "below_horizon"]), elevation=rng.uniform(-30, 60))
    options = {"target_temperature": rng.randint(18, 27), "portable_ac": pick([True, False, False]),
               "quiet_hours": pick([True, False]), "quiet_start": "00:00", "quiet_end": "23:59",
               "min_change_interval": pick([0, 180]), "compressor_min_cycle": pick([0, 300]),
               "device_min_cycle": pick([0, 120]), "coil_dry_out": pick([0, 120]),
               "ionizer_mode": pick(["with_purifier", "surge", "never"]), "away_max_drift": pick([0, 4]),
               "fan_comfort": pick([True, False]), "presence_hold": pick([0, 5])}
    options["quiet_precool"] = pick([True, False])
    home = Home.from_states(states, data, options, unit)
    if rng.random() < 0.4:                                             # a room the engine has already learned
        model = ThermalModel()
        model.restore(_TAUGHT)
        model.unit_offset, model._offset_count = rng.uniform(-4, 4), 50
        home.coordinator.thermal = model
    return home


def _check(home):
    data = home.data_now
    decision, raw, snap = data["decision"], data["raw_decision"], data["snapshot"]
    target, air = data["evaluations"]["target"], data["evaluations"]["air_quality"]
    options = home.coordinator.options
    context = f"\nconfig={home.data}\noptions={home.entry.options}\ndecision={decision}\ncalls={home.calls}"

    # Safety: an unvented compressor is never asked for, decided, or sent.
    if snap.vent_required and not snap.vented:
        assert raw.hvac_mode not in COMPRESSOR and decision.hvac_mode not in COMPRESSOR, "compressor decided unvented" + context
        assert not any(c[0] == "set_hvac_mode" and c[2].get("hvac_mode") in COMPRESSOR for c in home.calls), "compressor sent unvented" + context
    # It never heats and never commands heat.
    assert decision.hvac_mode != "heat" and not any(c[2].get("hvac_mode") == "heat" for c in home.calls), "heat" + context
    # The driven setpoint is a whole degree, at most 2 below the user's number, never above it.
    assert options.target - 2 <= target.effective_target <= options.target, "setpoint out of range" + context
    assert target.effective_target == int(target.effective_target)
    # Learning can only cool harder: a cycle never runs more than a degree under the driven
    # setpoint's floor, and the setpoint sent to the unit is never above the driven one.
    assert options.target - 2 <= target.stop_at <= target.effective_target, "stop point out of range" + context
    assert target.unit_setpoint <= target.effective_target, "compensation raised the setpoint" + context
    for service, entity_id, payload in home.calls:
        if service == "set_temperature":
            limits = home.states[entity_id].attributes
            assert limits["min_temp"] <= payload["temperature"] <= limits["max_temp"], "setpoint outside the unit's range" + context
    # A safety block stops cooling and the fan.
    if raw.blocked:
        assert raw.hvac_mode == "off" and raw.fan_action == "off", "blocked but running" + context
    # Ozone: the ionizer is only ever started in a room known to be empty.
    if raw.ionizer_action == "on":
        assert snap.occupancy is False, "ionizer with someone home" + context
    # Sealed means sealed.
    if air.seal:
        assert raw.ventilation_action != "on", "ventilating into bad outdoor air" + context
    # A device of unknown type never adds moisture.
    if snap.humidifier_class is None:
        assert raw.humidifier_action != "on", "unknown humidifier started" + context
    # Fan and purifier: an entity in the purifier slot is never driven by the fan channel,
    # and nothing but its own channel touches the purifier.
    purifiers = set(home.data.get("purifier_entity", []))
    if raw.purifier_action == "none" and decision.purifier_action == "none" and decision.purifier_speed is None:
        assert not any(c[1] in purifiers for c in home.calls), "purifier touched with no purifier decision" + context
    # Above the setpoint with a free compressor means COOL.
    caps = data["capabilities"]
    if (caps.climate and snap.climate_valid and snap.temperature_valid and snap.occupancy and not raw.blocked
            and snap.indoor_temp > options.target and "cool" in snap.hvac_modes):
        vented = not snap.vent_required or snap.vented
        feels = snap.feels_like if snap.feels_like is not None else snap.indoor_temp
        quiet = snap.quiet and feels < options.quiet_max_temp
        free_air = (caps.windows and snap.window_open and snap.outdoor_temp is not None
                    and snap.outdoor_temp < snap.indoor_temp and not options.portable_ac and not air.seal)
        if vented and not quiet and not free_air:
            assert raw.hvac_mode == "cool", "above setpoint, free to cool, not cooling" + context
    # Idempotent: applying the same decision again sends nothing (unless a device is unreachable).
    unreachable = any(s.state in ("unavailable", "unknown", "opening") for s in home.states.values())
    home.calls.clear()
    import asyncio
    asyncio.new_event_loop().run_until_complete(home.coordinator.async_apply_decision())
    if not decision.blocked and not unreachable:
        assert home.calls == [], "re-applying an unchanged decision sent commands" + context


def test_random_homes():
    rng = random.Random(20261003)
    for _ in range(600):
        home = _random_home(rng)
        for cycle in range(4):
            if cycle:
                for entity_id, state in home.states.items():
                    if entity_id == "sensor.temp" and state.state not in ("unavailable", "unknown"):
                        state.state = str(float(state.state) + rng.uniform(-3, 3))
                    elif entity_id == "binary_sensor.vent":
                        state.state = rng.choice(["on", "off"])
                    elif entity_id == "sensor.pm25":
                        state.state = str(rng.uniform(0, 200))
            home.cycle()
            _check(home)


@pytest.mark.parametrize("target", [22, 24])
def test_a_summer_day(monkeypatch, target):
    """13 C at night, 31 C mid-afternoon, a room that gains heat from outdoors, the sun and
    the people in it, and an AC that removes 0.12 C a minute. One-minute steps for 24 h."""
    clock = Clock(datetime(2026, 7, 15, 6, 0, tzinfo=timezone.utc)).install(monkeypatch)
    home = Home(temp=24.0, humidity=45.0, outdoor=20.0, ac=True, fan=True, purifier=True, pm25=3,
                occupancy="on", options={"target_temperature": target})
    room = 24.0
    over, compressor_starts, was_running, purifier_on = 0, 0, False, 0
    for minute in range(24 * 60):
        hour = (6 + minute / 60) % 24
        outdoor = 22 + 9 * math.sin((hour - 9) / 24 * 2 * math.pi)
        ac = home.states["climate.ac"]
        cooling = ac.state == "cool"
        room += 0.004 * (outdoor - room) + (0.01 if 9 <= hour < 19 else 0) + 0.004 - (0.12 if cooling else 0)
        home.set("weather.home", temperature=outdoor)
        home.set("sun.sun", "above_horizon" if 5 <= hour < 21 else "below_horizon")
        home.set("sensor.temp", f"{room:.2f}")
        home.set("sensor.pm25", 1 + (minute % 3))                 # clean air with sensor flicker
        home.cycle()
        clock.advance(60)
        running = ac.state in COMPRESSOR
        compressor_starts += running and not was_running
        was_running = running
        purifier_on += home.state("fan.purifier") == "on"
        if minute > 60 and room > target + 1.0:
            over += 1
        sent = ac.attributes["temperature"]
        assert sent <= target and sent == int(sent)
        assert ac.state != "heat"
    assert over == 0, f"room spent {over} minutes more than 1 C above the setpoint"
    assert compressor_starts <= 60, f"compressor started {compressor_starts} times in one day"
    assert purifier_on == 0, "purifier ran in clean air"

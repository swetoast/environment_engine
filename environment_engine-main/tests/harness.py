"""A fake Home Assistant that the REAL coordinator runs against.

Every test in this suite goes through the whole pipeline: entity states in, service calls
out. `Home` builds a room from keyword arguments, `cycle()` runs one update and applies
the decision, and service calls land back on the fake states the way a real device would
report them.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone

import custom_components.environment_engine.hysteresis as _hysteresis
from custom_components.environment_engine.coordinator import EnvironmentCoordinator
from homeassistant.util import dt as dt_util


class State:
    def __init__(self, entity_id, state, **attributes):
        self.entity_id = entity_id
        self.domain = entity_id.split(".", 1)[0]
        self.state = str(state)
        self.attributes = attributes


class _States(dict):
    """`hass.states`: a dict of State with the one extra method the integration calls."""

    def async_all(self, domain=None):
        return [s for s in self.values() if domain is None or s.domain == domain]


class Clock:
    """One controllable clock for the engine's rate limits, holds and forecasts."""

    def __init__(self, start=None):
        self.now = start or datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)

    def install(self, monkeypatch):
        clock = self

        class _Now(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.now

        monkeypatch.setattr(_hysteresis, "datetime", _Now)
        monkeypatch.setattr(dt_util, "utcnow", lambda: clock.now)
        monkeypatch.setattr(dt_util, "now", lambda: clock.now)
        return self


class _Entry:
    entry_id = "room"
    title = "Room"

    def __init__(self, data, options):
        self.data = data
        self.options = options


AC_MODES = ["off", "cool", "dry", "fan_only", "heat"]


class Home:
    """A room. Pass only what the scenario needs; everything else is left out, exactly as
    a real user would leave a slot empty.

        Home(temp=27, ac=True, fan=True, purifier=True, pm25=3, options={...})
    """

    def __init__(self, *, temp=22.0, humidity=45.0, outdoor=None, ac=False, ac_modes=None, fan=False,
                 purifier=False, ionizer=False, pm25=None, aqi=None, co2=None, outdoor_aqi=None,
                 outdoor_gas=None, occupancy=None, window=None, vent=None, smoke=None, humidifier=None,
                 ventilation=False, sun="above_horizon", unit="°C", options=None, extra=None):
        self.states = _States()
        self.calls: list[tuple] = []
        self.unit = unit
        data = {"entry_type": "room"}

        def add(slot, entity_id, state, **attrs):
            self.states[entity_id] = State(entity_id, state, **attrs)
            if slot:
                data.setdefault(slot, []).append(entity_id)

        add("temperature_sensor", "sensor.temp", temp, unit_of_measurement=unit)
        if humidity is not None:
            add("humidity_sensor", "sensor.humidity", humidity)
        if ac:
            add("climate_entity", "climate.ac", "off", hvac_modes=list(ac_modes or AC_MODES), min_temp=self._dev(16),
                max_temp=self._dev(31), target_temp_step=1, supported_features=385,
                current_temperature=temp, temperature=self._dev(24))
        if fan:
            add("fan_entity", "fan.room", "off", supported_features=48)
        if purifier:
            add("purifier_entity", "fan.purifier", "off", supported_features=49, percentage_step=33.33, percentage=0)
        if ionizer:
            add("ionizer_entity", "switch.ionizer", "off")
        if pm25 is not None:
            add("pm25_sensor", "sensor.pm25", pm25)
        if aqi is not None:
            add("aqi_sensor", "sensor.aqi", aqi)
        if co2 is not None:
            add("co2_sensor", "sensor.co2", co2)
        if outdoor_aqi is not None:
            add("outdoor_aqi_sensor", "sensor.outdoor_aqi", outdoor_aqi)
        if outdoor_gas is not None:
            add("outdoor_gas_sensor", "sensor.outdoor_gas", outdoor_gas)
        if outdoor is not None:
            add("weather_entity", "weather.home", "sunny", temperature=outdoor, temperature_unit=unit)
        if occupancy is not None:
            add("occupancy_entity", "binary_sensor.presence", occupancy)
        if window is not None:
            add("window_entity", "binary_sensor.window", window)
        if vent is not None:
            add("vent_entity", "binary_sensor.vent", vent)
        if smoke is not None:
            add("smoke_sensor", "binary_sensor.smoke", smoke)
        if humidifier is not None:
            add("humidifier_entity", "humidifier.unit", "off", device_class=humidifier or None)
        if ventilation:
            add("ventilation_entity", "fan.erv", "off")
        add(None, "sun.sun", sun, elevation=40 if sun == "above_horizon" else -20)
        for state in extra or ():
            self.states[state.entity_id] = state
        self._start(data, options)

    def _start(self, data, options):
        self.data = data
        self.entry = _Entry(data, {"auto_apply": True, "presence_hold": 0, **(options or {})})
        self.coordinator = EnvironmentCoordinator(self, self.entry)

    @classmethod
    def from_states(cls, states, data, options=None, unit="°C"):
        """A room from an explicit list of states and a config mapping (used by the fuzzer)."""
        home = cls.__new__(cls)
        home.states = _States((s.entity_id, s) for s in states)
        home.calls = []
        home.unit = unit
        home._start({"entry_type": "room", **data}, options)
        return home

    # --- the slice of the hass API the integration touches ---
    @property
    def services(self):
        return self

    @property
    def config(self):
        unit = self.unit
        return type("Config", (), {"units": type("Units", (), {"temperature_unit": unit})()})()

    @property
    def config_entries(self):
        return type("Entries", (), {"async_entries": staticmethod(lambda domain: [])})()

    async def async_call(self, domain, service, data, blocking=False):
        entity_id = data["entity_id"]
        self.calls.append((service, entity_id, {k: v for k, v in data.items() if k != "entity_id"}))
        target = self.states[entity_id]
        if service in ("turn_on", "open_cover"):
            target.state = "on" if service == "turn_on" else "open"
        elif service in ("turn_off", "close_cover"):
            target.state = "off" if service == "turn_off" else "closed"
        elif service == "set_hvac_mode":
            target.state = data["hvac_mode"]
        elif service == "set_temperature":
            target.attributes["temperature"] = data["temperature"]
        if "percentage" in data:
            target.attributes["percentage"] = data["percentage"]

    def _dev(self, celsius):
        return round(celsius * 9 / 5 + 32) if self.unit == "°F" else celsius

    # --- driving it ---
    def set(self, entity_id, state=None, **attributes):
        if state is not None:
            self.states[entity_id].state = str(state)
        self.states[entity_id].attributes.update(attributes)

    def state(self, entity_id):
        return self.states[entity_id].state

    def cycle(self, apply=True, force=False):
        """One engine update (and apply). Returns the decision; `self.calls` holds only the
        service calls this cycle made."""
        self.calls.clear()
        coordinator = self.coordinator

        async def run():
            coordinator.data = await coordinator._async_update_data()
            if apply:
                await coordinator.async_apply_decision(force=force)

        asyncio.new_event_loop().run_until_complete(run())
        return coordinator.data["decision"]

    @property
    def data_now(self):
        return self.coordinator.data

    def touched(self, entity_id):
        return [c for c in self.calls if c[1] == entity_id]


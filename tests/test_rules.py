"""The rules of the engine, end to end.

Each test builds a room, runs the real coordinator against it and checks what was actually
sent to the devices. One test per rule the engine promises; if one of these fails, the
engine is breaking a promise in the README.
"""
import pytest
from harness import Clock, Home, State


@pytest.fixture
def clock(monkeypatch):
    return Clock().install(monkeypatch)


# --------------------------------------------------------------------------- cooling

def test_above_the_setpoint_means_cool_and_nothing_talks_it_out_of_it(clock):
    """Night, dark, expensive power: a room above the setpoint is still cooled, to a whole
    degree that is never above the number the user asked for."""
    price = State("sensor.price", 3.0)
    lux = State("sensor.lux", 0)
    home = Home(temp=25.0, outdoor=20.0, ac=True, sun="below_horizon", extra=[price, lux],
                options={"target_temperature": 22})
    home.data["price_entity"] = ["sensor.price"]
    home.data["lux_sensor"] = ["sensor.lux"]
    decision = home.cycle()
    assert home.state("climate.ac") == "cool"
    sent = home.states["climate.ac"].attributes["temperature"]
    assert sent == int(sent) and 20 <= sent <= 22
    assert decision.target_temperature <= 22

    # At or below the setpoint with nothing else wrong: the unit is left off.
    cool = Home(temp=21.5, outdoor=20.0, ac=True, options={"target_temperature": 22})
    cool.cycle()
    assert cool.state("climate.ac") == "off" and cool.calls == []


def test_the_engine_never_heats_and_never_touches_a_heating_unit(clock):
    home = Home(temp=15.0, outdoor=0.0, ac=True, options={"target_temperature": 22})
    home.set("climate.ac", "heat")
    home.cycle()
    assert home.state("climate.ac") == "heat" and home.calls == []


def test_a_cycle_starts_at_the_users_number_and_finishes_at_the_driven_one(clock):
    """Hot outside drives the setpoint below the user's. Cooling starts above 22 and, once
    running, continues to the driven setpoint instead of stopping the instant 22 is touched."""
    home = Home(temp=22.4, outdoor=35.0, ac=True, options={"target_temperature": 22, "compressor_min_cycle": 0, "coil_dry_out": 0})
    home.cycle()
    driven = home.states["climate.ac"].attributes["temperature"]
    assert home.state("climate.ac") == "cool" and driven < 22
    clock.advance(600)
    home.set("sensor.temp", 21.8)
    home.cycle()
    assert home.state("climate.ac") == "cool"            # under 22 but not yet at the driven setpoint
    clock.advance(600)
    home.set("sensor.temp", driven)
    home.cycle()
    assert home.state("climate.ac") == "off"
    clock.advance(600)
    home.set("sensor.temp", 21.8)
    home.cycle()
    assert home.state("climate.ac") == "off"             # does not restart below the user's number


def test_fahrenheit_units_are_converted_both_ways(clock):
    home = Home(temp=80.6, outdoor=68.0, ac=True, unit="°F", options={"target_temperature": 22})   # 27 C
    home.cycle()
    assert home.state("climate.ac") == "cool"
    sent = home.states["climate.ac"].attributes["temperature"]
    assert sent == int(sent) and 66 <= sent <= 72        # 19..22 C, floored in the unit's own scale


# --------------------------------------------------------------------------- compressor gates

@pytest.mark.parametrize("portable_option, vent_sensor", [(True, None), (False, "off"), (True, "off")])
def test_an_unvented_unit_never_runs_its_compressor(clock, portable_option, vent_sensor):
    """Cool AND dry are blocked until the exhaust is confirmed vented, whether the gate comes
    from the Portable AC option or from a wired vent sensor. Fan-only stands in."""
    home = Home(temp=29.0, humidity=80.0, outdoor=25.0, ac=True, vent=vent_sensor,
                options={"target_temperature": 22, "portable_ac": portable_option})
    for _ in range(3):
        decision = home.cycle()
        clock.advance(600)
        assert home.state("climate.ac") == "fan_only"
        assert decision.hvac_mode not in ("cool", "dry")
    home.set("sensor.temp", 21.0)                         # cool but very damp: DRY would be next
    home.cycle()
    assert home.state("climate.ac") not in ("cool", "dry")


def test_closing_the_vent_stops_the_compressor_at_once_despite_the_minimum_cycle(clock):
    home = Home(temp=29.0, outdoor=25.0, ac=True, vent="on", options={"target_temperature": 22})
    home.cycle()
    assert home.state("climate.ac") == "cool"
    clock.advance(60)                                     # well inside min cycle and rate limit
    home.set("binary_sensor.vent", "off")
    decision = home.cycle()
    assert home.state("climate.ac") == "fan_only" and decision.hvac_mode == "fan_only"


def test_quiet_hours_fan_instead_of_compressor_until_it_is_too_hot(clock):
    options = {"target_temperature": 22, "quiet_hours": True, "quiet_start": "00:00", "quiet_end": "23:59",
               "quiet_max_temp": 26.0}
    home = Home(temp=24.0, humidity=40.0, outdoor=20.0, ac=True, options=options)
    assert home.cycle().strategy == "quiet_cooling" and home.state("climate.ac") == "fan_only"
    normal = Home(temp=21.0, humidity=40.0, outdoor=20.0, ac=True, options=options)
    normal.cycle()
    assert normal.state("climate.ac") == "off"            # normal temperature: nothing starts
    hot = Home(temp=27.0, humidity=40.0, outdoor=20.0, ac=True, options=options)
    hot.cycle()
    assert hot.state("climate.ac") == "cool"              # past the limit the compressor runs


def test_compressor_protection_stop_is_immediate_restart_waits_and_the_coil_is_dried(clock):
    home = Home(temp=24.0, outdoor=20.0, ac=True, options={"target_temperature": 22, "compressor_min_cycle": 300,
                                                            "coil_dry_out": 120, "min_change_interval": 0})
    home.cycle()
    assert home.state("climate.ac") == "cool"
    clock.advance(400)
    home.set("sensor.temp", 21.5)
    home.cycle()
    assert home.state("climate.ac") == "fan_only"         # compressor off, blower drying the coil
    clock.advance(60)
    home.set("sensor.temp", 23.0)
    home.cycle()
    assert home.state("climate.ac") == "fan_only"         # restart inside the minimum cycle: wait, moving air
    clock.advance(300)
    home.cycle()
    assert home.state("climate.ac") == "cool"
    clock.advance(400)
    home.set("sensor.temp", 21.5)
    home.cycle()
    clock.advance(200)
    home.cycle()
    assert home.state("climate.ac") == "off"              # dry-out finished


# --------------------------------------------------------------------------- safety

def test_smoke_stops_cooling_and_fans_and_keeps_them_stopped(clock):
    home = Home(temp=29.0, outdoor=25.0, ac=True, fan=True, smoke="off", options={"target_temperature": 22})
    home.cycle()
    assert home.state("climate.ac") == "cool" and home.state("fan.room") == "on"
    clock.advance(30)
    home.set("binary_sensor.smoke", "on")
    decision = home.cycle()
    assert decision.blocked and decision.strategy == "safety_stop"
    assert home.state("climate.ac") == "off" and home.state("fan.room") == "off"
    home.set("climate.ac", "cool")                        # someone turns it back on by hand
    home.cycle()
    assert home.state("climate.ac") == "off"              # a block is re-asserted every cycle


def test_lightning_inside_the_radius_holds_everything(clock):
    strike = State("geo_location.lightning_strike_1", 12.0, source="blitzortung", unit_of_measurement="km",
                   publication_date=clock.now.isoformat(), external_id="s1")
    marker = State("sensor.blitzortung_distance", "unknown")
    home = Home(temp=29.0, outdoor=25.0, ac=True, extra=[strike, marker], options={"target_temperature": 22})
    home.data["lightning_distance_sensor"] = ["sensor.blitzortung_distance"]
    decision = home.cycle()
    assert decision.blocked and "lightning" in decision.reason and home.state("climate.ac") == "off"


# --------------------------------------------------------------------------- fan and purifier

def test_fan_and_purifier_are_decoupled(clock):
    """Heat moves the fan and never the purifier. Bad air moves the purifier and never the
    fan. Changing one device never re-sends the other."""
    hot = Home(temp=27.0, outdoor=20.0, ac=True, fan=True, purifier=True, pm25=3, options={"target_temperature": 22})
    hot.cycle()
    assert hot.state("fan.room") == "on" and hot.state("fan.purifier") == "off"
    assert hot.touched("fan.purifier") == []

    dirty = Home(temp=21.0, outdoor=20.0, ac=True, fan=True, purifier=True, pm25=120, options={"target_temperature": 22})
    dirty.cycle()
    assert dirty.state("fan.purifier") == "on" and dirty.state("fan.room") == "off"
    assert dirty.touched("fan.room") == []

    # The purifier is switched off by hand; the fan starting later must not bring it back.
    dirty.set("fan.purifier", "off")
    clock.advance(600)
    dirty.set("sensor.temp", 27.0)
    dirty.cycle()
    assert dirty.state("fan.room") == "on" and dirty.touched("fan.purifier") == []


def test_sensor_noise_in_clean_air_never_starts_the_purifier(clock):
    home = Home(temp=21.0, fan=True, purifier=True, pm25=2, aqi=17)
    for reading in (2, 1, 3, 1, 2, 1, 4, 1):
        home.set("sensor.pm25", reading)
        decision = home.cycle()
        clock.advance(60)
        assert home.state("fan.purifier") == "off" and home.state("fan.room") == "off"
        assert decision.purifier_action != "on"


def test_a_real_particle_event_is_cleaned_held_through_its_tail_and_released(clock):
    home = Home(temp=21.0, purifier=True, pm25=150, options={"air_recovery": 10, "min_change_interval": 0, "device_min_cycle": 0})
    home.cycle()
    assert home.state("fan.purifier") == "on" and home.states["fan.purifier"].attributes["percentage"] == 100
    clock.advance(120)
    home.set("sensor.pm25", 4)
    home.cycle()
    assert home.state("fan.purifier") == "on"             # still clearing the tail
    clock.advance(3600)
    home.cycle()
    assert home.state("fan.purifier") == "off"            # hold decayed, air clean


def test_one_entity_in_both_slots_is_treated_as_the_purifier(clock):
    home = Home(temp=28.0, outdoor=20.0, purifier=True, pm25=2)
    home.data["fan_entity"] = ["fan.purifier"]
    home.cycle()
    assert home.state("fan.purifier") == "off"            # heat did not start the purifier
    assert any("in both" in problem for problem in home.data_now["snapshot"].invalid_entities)


def test_ionizer_only_runs_in_an_empty_room(clock):
    home = Home(temp=21.0, purifier=True, ionizer=True, pm25=150, occupancy="on")
    home.cycle()
    assert home.state("fan.purifier") == "on" and home.state("switch.ionizer") == "off"
    clock.advance(600)
    home.set("binary_sensor.presence", "off")
    home.cycle()
    assert home.state("switch.ionizer") == "on"
    clock.advance(600)
    home.set("binary_sensor.presence", "on")
    home.cycle()
    assert home.state("switch.ionizer") == "off"


# --------------------------------------------------------------------------- outdoor air

def test_outdoor_smoke_seals_and_purifies_but_outdoor_gas_only_seals(clock):
    smoke = Home(temp=21.0, purifier=True, ventilation=True, pm25=3, co2=1500, outdoor_aqi=180)
    decision = smoke.cycle()
    assert smoke.state("fan.erv") == "off" and smoke.state("fan.purifier") == "on"
    assert decision.ventilation_action == "off"

    gas = Home(temp=21.0, purifier=True, ventilation=True, pm25=3, co2=1500, outdoor_gas=0.9)
    decision = gas.cycle()
    assert decision.ventilation_action == "off"            # sealed
    assert gas.state("fan.purifier") == "off"              # a filter cannot remove a gas

    fresh = Home(temp=21.0, purifier=True, ventilation=True, pm25=3, co2=1500, outdoor_aqi=20)
    fresh.cycle()
    assert fresh.state("fan.erv") == "on"                  # stuffy room, clean outside: air it


# --------------------------------------------------------------------------- humidity

def test_damp_air_at_setpoint_is_dried_and_dry_air_is_left_alone(clock):
    damp = Home(temp=21.5, humidity=80.0, outdoor=20.0, ac=True, options={"target_temperature": 22})
    assert damp.cycle().strategy == "dehumidify" and damp.state("climate.ac") == "dry"
    dry = Home(temp=21.5, humidity=40.0, outdoor=20.0, ac=True, options={"target_temperature": 22})
    dry.cycle()
    assert dry.state("climate.ac") == "off"
    # Above the setpoint, cooling wins: the coil dries the air on the way down.
    both = Home(temp=26.0, humidity=80.0, outdoor=20.0, ac=True, options={"target_temperature": 22})
    both.cycle()
    assert both.state("climate.ac") == "cool"


def test_a_humidifier_is_never_started_on_a_guess(clock):
    unknown = Home(temp=21.0, humidity=20.0, humidifier="")
    unknown.cycle()
    assert unknown.state("humidifier.unit") == "off"
    known = Home(temp=21.0, humidity=20.0, humidifier="humidifier")
    known.cycle()
    assert known.state("humidifier.unit") == "on"


# --------------------------------------------------------------------------- away

def test_an_empty_home_idles_but_caps_the_heat_and_still_cleans_the_air(clock):
    options = {"target_temperature": 22, "away_max_drift": 4}
    home = Home(temp=25.0, outdoor=24.0, ac=True, fan=True, purifier=True, pm25=3, occupancy="on", options=options)
    home.cycle()
    assert home.state("climate.ac") == "cool" and home.state("fan.room") == "on"
    clock.advance(900)
    home.set("binary_sensor.presence", "off")
    assert home.cycle().strategy == "away_idle"
    assert home.state("fan.room") == "off" and home.state("climate.ac") in ("off", "fan_only")
    clock.advance(900)
    home.set("sensor.temp", 27.0)                         # past 22 + 4
    home.cycle()
    assert home.state("climate.ac") == "cool" and home.states["climate.ac"].attributes["temperature"] == 26
    clock.advance(900)
    home.set("sensor.pm25", 150)
    home.cycle()
    assert home.state("fan.purifier") == "on"             # air quality does not need anyone home
    clock.advance(7200)
    home.set("sensor.pm25", 2)
    home.cycle()
    assert home.state("fan.purifier") == "off"            # and it is switched off again when clean


# --------------------------------------------------------------------------- delivery

def test_commands_are_sent_once_retried_when_a_device_was_offline_and_forced_on_request(clock):
    home = Home(temp=27.0, outdoor=20.0, ac=True, fan=True, options={"target_temperature": 22})
    home.set("fan.room", "unavailable")
    home.cycle()
    assert home.state("climate.ac") == "cool" and home.touched("fan.room") == []
    home.cycle()
    assert home.calls == []                               # unchanged decision: nothing re-sent
    home.set("fan.room", "off")                           # the fan comes back
    home.cycle()
    assert home.state("fan.room") == "on"                 # and gets the command it missed
    home.set("climate.ac", "off")                         # switched off by hand
    home.cycle()
    assert home.state("climate.ac") == "off"              # the engine does not fight a manual change...
    home.cycle(force=True)
    assert home.state("climate.ac") == "cool"             # ...until Apply Decision is pressed


def test_auto_apply_off_decides_but_changes_nothing(clock):
    home = Home(temp=27.0, outdoor=20.0, ac=True, fan=True, options={"target_temperature": 22, "auto_apply": False})
    decision = home.cycle(apply=False)
    assert decision.hvac_mode == "cool" and home.coordinator._auto_apply_pending is False
    assert home.calls == [] and home.state("climate.ac") == "off"


def test_a_dead_temperature_sensor_never_switches_a_running_unit(clock):
    home = Home(temp=27.0, outdoor=20.0, ac=True, options={"target_temperature": 22})
    home.states["climate.ac"].attributes.pop("current_temperature")
    home.cycle()
    assert home.state("climate.ac") == "cool"
    clock.advance(600)
    home.set("sensor.temp", "unavailable")
    home.cycle()
    assert home.state("climate.ac") == "cool" and home.calls == []

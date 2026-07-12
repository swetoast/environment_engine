"""Regression tests for the audit fixes."""
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.const import ACTION_NONE, ACTION_OPEN, ACTION_CLOSE
from custom_components.environment_engine.evaluators import (
    evaluate_air_quality, evaluate_energy, evaluate_humidity, evaluate_mold,
    evaluate_safety, evaluate_solar, evaluate_thermal,
)
from custom_components.environment_engine.planner import Planner
from custom_components.environment_engine.snapshot import Snapshot
from custom_components.environment_engine.thermal_memory import ThermalMemory

MEM = ThermalMemory()


def _opts():
    return make_options()


def _caps(**kw):
    base = dict(climate=False, temperature=False, humidity=False, weather=False,
                occupancy=False, windows=False, pricing=False, air_quality=False,
                blinds=False, illuminance=False, fan=False, purifier=False, humidifier=False, ionizer=False, ventilation=False, smoke=False,
                lightning=False, outlet_overload=False)
    base.update(kw)
    return Capabilities(**base)


def _snap(**kw):
    d = dict(indoor_temp=22.0, humidity=50.0, outdoor_temp=18.0, occupancy=True,
             window_open=False, energy_price=None, co2=None, voc=None,
             hvac_mode="off", hvac_modes=["off", "cool", "dry", "fan_only", "heat"],
             min_temp=16, max_temp=30, sun_up=True,
             smoke_detected=False, outlet_overloaded=False,
             temperature_valid=True, climate_valid=True, cover_closed=False, invalid_entities=[])
    d.update(kw)
    return Snapshot(**d)


def _plan(caps, snap, opts=None):
    opts = opts or _opts()
    solar = evaluate_solar(snap, opts)
    energy = evaluate_energy(snap, opts)
    ev = {
        "safety": evaluate_safety(snap, caps, opts), "solar": solar, "energy": energy,
        "thermal": evaluate_thermal(snap, MEM, solar.pressure, energy.penalty, 0.0, opts.target),
        "humidity": evaluate_humidity(snap, MEM, 0.0), "mold": evaluate_mold(snap, MEM),
        "air_quality": evaluate_air_quality(snap, opts),
    }
    return Planner(caps, opts).plan(snap, ev)


def test_purifier_untouched_without_air_quality_sensor():
    caps = _caps(purifier=True)  # purifier but no co2/voc sensor
    assert _plan(caps, _snap()).purifier_action == ACTION_NONE


def test_blinds_close_on_solar_load():
    caps = _caps(blinds=True, weather=True)
    assert _plan(caps, _snap(outdoor_temp=31.0)).cover_action == ACTION_CLOSE


def test_blinds_reopen_in_daylight_when_load_clears():
    caps = _caps(blinds=True, weather=True)
    snap = _snap(outdoor_temp=17.0, sun_up=True, cover_closed=True)
    assert _plan(caps, snap).cover_action == ACTION_OPEN


def test_blinds_not_reopened_at_night():
    caps = _caps(blinds=True, weather=True)
    snap = _snap(outdoor_temp=17.0, sun_up=False, cover_closed=True)
    assert _plan(caps, snap).cover_action == ACTION_NONE



def test_configurable_voc_threshold_brings_low_range_sensors_to_life():
    # default 250 -> a reading of 96 is dead; lower the threshold and it registers
    snap = _snap(voc=96.0)
    assert evaluate_air_quality(snap, _opts()).pressure == 0.0
    tuned = make_options(voc_threshold=60)
    assert evaluate_air_quality(snap, tuned).pressure > 0.0


def test_lux_glare_closes_blinds_even_when_not_hot():
    caps = _caps(blinds=True, weather=True, illuminance=True)
    # cool outside (no heat load) but very bright -> shade for glare
    snap = _snap(outdoor_temp=16.0, sun_up=True, lux=2500.0)
    assert _plan(caps, snap).cover_action == ACTION_CLOSE


def test_lux_below_threshold_does_not_close():
    caps = _caps(blinds=True, weather=True, illuminance=True)
    snap = _snap(outdoor_temp=16.0, sun_up=True, lux=226.0)  # Toast's typical reading
    assert _plan(caps, snap).cover_action == ACTION_NONE


def test_lux_reopen_only_at_dusk_not_in_daylight():
    caps = _caps(blinds=True, weather=True, illuminance=True)
    # bright sensor would read low once closed; daylight must NOT reopen (no oscillation)
    daylight = _snap(outdoor_temp=16.0, sun_up=True, lux=150.0, cover_closed=True)
    assert _plan(caps, daylight).cover_action == ACTION_NONE
    dusk = _snap(outdoor_temp=16.0, sun_up=False, lux=0.0, cover_closed=True)
    assert _plan(caps, dusk).cover_action == ACTION_OPEN


def test_heat_only_blinds_still_daylight_reopen_without_lux():
    caps = _caps(blinds=True, weather=True)  # no illuminance
    snap = _snap(outdoor_temp=17.0, sun_up=True, cover_closed=True)
    assert _plan(caps, snap).cover_action == ACTION_OPEN

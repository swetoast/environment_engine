"""Planner = composition of four independent actuator resolvers.

These assert the design contract: each actuator is gated only on its own
capability, so the engine does the most useful thing with whatever devices
exist -- no actuator is privileged.
"""
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.const import (
    ACTION_NONE, ACTION_ON, HVAC_COOL,
    STRATEGY_AIR_CIRCULATION, STRATEGY_AIR_QUALITY, STRATEGY_CLIMATE_OFFLINE,
    STRATEGY_COOLING, STRATEGY_PASSIVE_VENTILATION, STRATEGY_SAFETY_STOP,
)
from custom_components.environment_engine.evaluators import (
    evaluate_air_quality, evaluate_energy, evaluate_humidity, evaluate_mold,
    evaluate_safety, evaluate_solar, evaluate_thermal,
)
from custom_components.environment_engine.planner import Planner
from custom_components.environment_engine.snapshot import Snapshot
from custom_components.environment_engine.thermal_memory import ThermalMemory

OPTS = make_options()
MEM = ThermalMemory()


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
             temperature_valid=True, climate_valid=True, invalid_entities=[])
    d.update(kw)
    return Snapshot(**d)


def _evals(snap, caps):
    solar = evaluate_solar(snap, OPTS)
    energy = evaluate_energy(snap, OPTS)
    return {
        "safety": evaluate_safety(snap, caps, OPTS),
        "solar": solar,
        "energy": energy,
        "thermal": evaluate_thermal(snap, MEM, solar.pressure, energy.penalty, 0.0),
        "humidity": evaluate_humidity(snap, MEM, 0.0),
        "mold": evaluate_mold(snap, MEM),
        "air_quality": evaluate_air_quality(snap, OPTS),
    }


def _plan(caps, snap):
    return Planner(caps, OPTS).plan(snap, _evals(snap, caps))


# --- capability degradation -------------------------------------------------

def test_minimal_setup_never_safety_stops():
    caps = _caps(humidity=True)
    snap = _snap(climate_valid=False, temperature_valid=False, hvac_modes=[], indoor_temp=0.0)
    assert _plan(caps, snap).strategy != STRATEGY_SAFETY_STOP


def test_smoke_still_hard_blocks():
    caps = _caps(climate=True, temperature=True, smoke=True)
    decision = _plan(caps, _snap(smoke_detected=True))
    assert decision.strategy == STRATEGY_SAFETY_STOP and decision.blocked is True


# --- a lone fan is a first-class actuator -----------------------------------

def test_fan_only_home_cools_by_circulation():
    caps = _caps(temperature=True, fan=True)  # no climate at all
    decision = _plan(caps, _snap(indoor_temp=27.0))
    assert decision.strategy == STRATEGY_AIR_CIRCULATION
    assert decision.hvac_mode is None  # never touches a climate it doesn't have
    assert decision.fan_action == ACTION_ON


def test_fan_runs_alongside_active_cooling_not_as_fallback():
    caps = _caps(climate=True, temperature=True, fan=True)
    decision = _plan(caps, _snap(indoor_temp=27.0))
    # climate cools AND the fan circulates -- co-equal, not either/or
    assert decision.strategy == STRATEGY_COOLING
    assert decision.hvac_mode == HVAC_COOL
    assert decision.fan_action == ACTION_ON


# --- a lone purifier ---------------------------------------------------------

def test_purifier_only_home_acts_without_climate():
    caps = _caps(purifier=True, air_quality=True)
    decision = _plan(caps, _snap(co2=1800.0))
    assert decision.strategy == STRATEGY_AIR_QUALITY
    assert decision.hvac_mode is None
    assert decision.fan_action == ACTION_NONE
    assert decision.purifier_action == ACTION_ON


# --- AC offline degrades, doesn't deadlock ----------------------------------

def test_ac_offline_with_fan_still_cools():
    caps = _caps(climate=True, temperature=True, fan=True)
    decision = _plan(caps, _snap(climate_valid=False, indoor_temp=27.0))
    assert decision.blocked is False
    assert decision.hvac_mode is None  # don't command a dead climate
    assert decision.fan_action == ACTION_ON


def test_ac_offline_idle_leaves_label_climate_offline():
    caps = _caps(climate=True, temperature=True, purifier=True)
    decision = _plan(caps, _snap(climate_valid=False))
    assert decision.strategy == STRATEGY_CLIMATE_OFFLINE
    assert decision.blocked is False


# --- the engine never fights a mode it does not manage ----------------------

def test_does_not_turn_off_a_heating_ac():
    caps = _caps(climate=True, temperature=True)
    snap = _snap(indoor_temp=18.0, hvac_mode="heat", hvac_modes=["off", "heat"])
    assert _plan(caps, snap).hvac_mode is None  # leaves heat alone


def test_heat_only_ac_does_not_get_forced_to_cool():
    caps = _caps(climate=True, temperature=True)
    snap = _snap(indoor_temp=30.0, hvac_modes=["off", "heat"])
    assert _plan(caps, snap).hvac_mode != HVAC_COOL


# --- ventilation -------------------------------------------------------------

def test_ventilation_prefers_passive_when_window_open():
    caps = _caps(climate=True, temperature=True, windows=True, fan=True, purifier=True, air_quality=True)
    snap = _snap(indoor_temp=27.0, outdoor_temp=24.0, window_open=True, co2=1900.0)
    decision = _plan(caps, snap)
    assert decision.strategy == STRATEGY_PASSIVE_VENTILATION
    assert decision.purifier_action == ACTION_ON


def test_ventilation_silent_without_thermal_pressure():
    caps = _caps(climate=True, temperature=True, windows=True, fan=True)
    snap = _snap(indoor_temp=21.0, outdoor_temp=19.0, window_open=True, humidity=40.0)
    assert _plan(caps, snap).strategy != STRATEGY_PASSIVE_VENTILATION

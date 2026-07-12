"""Dehumidifier / humidifier actuator resolution."""
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.const import ACTION_NONE, ACTION_OFF, ACTION_ON, HVAC_DRY, STRATEGY_DEHUMIDIFY, STRATEGY_HUMIDIFY
from custom_components.environment_engine.evaluators import evaluate_humidity, evaluate_mold
from custom_components.environment_engine.resolvers import resolve_climate, resolve_humidifier
from custom_components.environment_engine.snapshot import Snapshot
from custom_components.environment_engine.thermal_memory import ThermalMemory

MEM = ThermalMemory()


def _opts():
    return make_options()


def _caps(**kw):
    base = dict(climate=False, temperature=False, humidity=False, weather=False, occupancy=False,
                windows=False, pricing=False, air_quality=False, blinds=False, illuminance=False,
                fan=False, purifier=False, humidifier=False, ionizer=False, ventilation=False, smoke=False, lightning=False, outlet_overload=False)
    base.update(kw)
    return Capabilities(**base)


def _snap(**kw):
    d = dict(indoor_temp=22.0, humidity=55.0, outdoor_temp=18.0, occupancy=True, window_open=False,
             energy_price=None, co2=None, voc=None, hvac_mode="off", hvac_modes=["off", "cool", "dry"],
             min_temp=16, max_temp=30, sun_up=True, smoke_detected=False, outlet_overloaded=False)
    d.update(kw)
    return Snapshot(**d)


def _ev(snap):
    return {"humidity": evaluate_humidity(snap, MEM, 0.0), "mold": evaluate_mold(snap, MEM)}


def test_dehumidifier_runs_when_humid():
    caps = _caps(humidifier=True, humidity=True)
    snap = _snap(humidity=72.0)  # high humidity -> drying pressure
    action, target, driver = resolve_humidifier(snap, caps, _opts(), _ev(snap))
    assert action == ACTION_ON
    assert target == 50
    assert driver == STRATEGY_DEHUMIDIFY


def test_dehumidifier_off_when_dry():
    caps = _caps(humidifier=True, humidity=True)
    snap = _snap(humidity=40.0)  # below target-5 -> turn off
    action, _, _ = resolve_humidifier(snap, caps, _opts(), _ev(snap))
    assert action == ACTION_OFF


def test_no_humidifier_capability_is_untouched():
    caps = _caps(humidity=True)  # sensor but no humidifier device
    snap = _snap(humidity=72.0)
    assert resolve_humidifier(snap, caps, _opts(), _ev(snap))[0] == ACTION_NONE


def test_humidifier_direction_adds_moisture_when_dry():
    caps = _caps(humidifier=True, humidity=True)
    snap = _snap(humidity=30.0, humidifier_class="humidifier")  # dry -> add moisture
    action, target, driver = resolve_humidifier(snap, caps, _opts(), _ev(snap))
    assert action == ACTION_ON
    assert driver == STRATEGY_HUMIDIFY


def test_dedicated_dehumidifier_frees_ac_from_dry_mode():
    # With a dehumidifier present, the AC should NOT switch to its dry mode;
    # drying is delegated so the AC can cool instead.
    snap = _snap(humidity=75.0, indoor_temp=21.0)
    ev = {"thermal": _T(0.1), "humidity": evaluate_humidity(snap, MEM, 0.0), "mold": evaluate_mold(snap, MEM)}
    with_dehum = _caps(climate=True, humidity=True, humidifier=True)
    hvac, _, _ = resolve_climate(snap, with_dehum, _opts(), ev, passive_cooling=False)
    assert hvac != HVAC_DRY
    without = _caps(climate=True, humidity=True)
    hvac2, _, driver2 = resolve_climate(snap, without, _opts(), ev, passive_cooling=False)
    assert hvac2 == HVAC_DRY


class _T:
    def __init__(self, c):
        self.confidence = c
        self.reason = "t"
        self.warming = False
        self.pressure = c

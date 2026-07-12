"""Climate resolver: portable-AC vent gating and AC fan_only for circulation."""
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.const import HVAC_COOL, HVAC_FAN_ONLY, HVAC_OFF
from custom_components.environment_engine.resolvers import resolve_climate
from custom_components.environment_engine.snapshot import Snapshot


def _opts(portable=False):
    return make_options(portable_ac=portable)


def _caps(fan=False, humidity=False, humidifier=False):
    base = dict(climate=True, temperature=True, humidity=humidity, weather=False, occupancy=False, windows=False,
                pricing=False, air_quality=False, blinds=False, illuminance=False, fan=fan, purifier=False,
                humidifier=humidifier, ionizer=False, ventilation=False, smoke=False, lightning=False, outlet_overload=False)
    return Capabilities(**base)


def _snap(modes=("off", "cool", "dry", "fan_only"), vented=False, portable=False, hvac_mode="off"):
    return Snapshot(indoor_temp=26.0, humidity=50.0, outdoor_temp=20.0, occupancy=True, window_open=False,
                    energy_price=None, co2=None, voc=None, hvac_mode=hvac_mode, hvac_modes=list(modes),
                    min_temp=16.0, max_temp=30.0, climate_valid=True, portable_ac=portable, vented=vented)


class _T:
    def __init__(self, c): self.confidence = c; self.reason = "t"


class _M:
    def __init__(self, risk=0.0, air=False): self.risk = risk; self.airflow_recommended = air; self.confidence = risk


class _H:
    def __init__(self, c=0.0): self.confidence = c


class _Tgt:
    effective_target = 23


def _ev(thermal=0.5, mold_air=False):
    return {"thermal": _T(thermal), "mold": _M(air=mold_air), "humidity": _H(), "target": _Tgt()}


def test_split_ac_cools_normally():
    mode, _, _ = resolve_climate(_snap(), _caps(), _opts(), _ev(0.5), False)
    assert mode == HVAC_COOL


def test_portable_vented_cools():
    mode, _, _ = resolve_climate(_snap(portable=True, vented=True), _caps(), _opts(True), _ev(0.5), False)
    assert mode == HVAC_COOL


def test_portable_unvented_falls_back_to_fan_only():
    mode, _, _ = resolve_climate(_snap(portable=True, vented=False), _caps(fan=False), _opts(True), _ev(0.5), False)
    assert mode == HVAC_FAN_ONLY  # circulate, don't dump condenser heat


def test_portable_unvented_with_standalone_fan_turns_ac_off():
    mode, _, _ = resolve_climate(_snap(portable=True, vented=False, hvac_mode="cool"), _caps(fan=True), _opts(True), _ev(0.5), False)
    assert mode == HVAC_OFF  # the standalone fan handles circulation


def test_ac_fan_only_circulates_when_no_standalone_fan():
    mode, _, _ = resolve_climate(_snap(modes=("off", "fan_only")), _caps(fan=False), _opts(), _ev(0.5), False)
    assert mode == HVAC_FAN_ONLY


def test_no_double_fanning_when_standalone_fan_present():
    mode, _, _ = resolve_climate(_snap(modes=("off", "fan_only")), _caps(fan=True), _opts(), _ev(0.5), False)
    assert mode != HVAC_FAN_ONLY  # standalone fan does it; AC stays out of it


def test_a_sensor_blip_does_not_stand_the_ac_down():
    """Regression: when the temperature sensor drops out the room reading is a substituted
    placeholder, not a measurement. Acting on it turned a happily-cooling AC OFF on a single
    bad cycle, and anti-short-cycling then delayed the restart. Hold instead -- the unit has
    its own thermostat and keeps regulating to the setpoint we last gave it."""
    snap = Snapshot(indoor_temp=0.0, humidity=50.0, outdoor_temp=30.0, occupancy=True, window_open=False,
                    energy_price=None, co2=None, voc=None, hvac_mode="cool",
                    hvac_modes=["off", "cool", "dry", "fan_only"], min_temp=16.0, max_temp=30.0,
                    climate_valid=True, temperature_valid=False)
    mode, target, driver = resolve_climate(snap, _caps(), _opts(), _ev(0.0), False)
    assert mode is None and target is None and driver is None  # hands off

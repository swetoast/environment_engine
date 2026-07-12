"""Effective climate target resolution and its flow into cooling."""
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.const import HVAC_COOL
from custom_components.environment_engine.resolvers import resolve_climate
from custom_components.environment_engine.snapshot import Snapshot
from custom_components.environment_engine.target_resolver import TargetResult, resolve_effective_target
from custom_components.environment_engine.thermal_memory import ThermalMemory


def _opts():
    return make_options()


def _snap(**kw):
    d = dict(indoor_temp=22.0, humidity=50.0, outdoor_temp=18.0, occupancy=True, window_open=False,
             energy_price=None, co2=None, voc=None, hvac_mode="off", hvac_modes=["off", "cool"],
             min_temp=16.0, max_temp=30.0, sun_up=True,
             smoke_detected=False, outlet_overloaded=False)
    d.update(kw)
    return Snapshot(**d)


def _mem(trend=0.0):
    m = ThermalMemory()
    m.temperature_trend = trend
    return m


def test_baseline_held_when_comfortable():
    r = resolve_effective_target(_snap(indoor_temp=22.0), _mem(), {}, _opts())
    assert r.effective_target == 22
    assert r.base_target == 22


def test_hot_room_lowers_setpoint():
    r = resolve_effective_target(_snap(indoor_temp=28.0), _mem(), {}, _opts())
    assert r.effective_target < 22
    assert r.cooling_drop > 0


def test_drop_is_bounded_and_saturating():
    r = resolve_effective_target(_snap(indoor_temp=45.0), _mem(), {}, _opts())
    assert r.cooling_drop <= 3.0  # never exceeds the cap
    assert r.effective_target >= 16  # device min


def test_warming_trend_adds_drop():
    calm = resolve_effective_target(_snap(indoor_temp=25.0), _mem(0.0), {}, _opts())
    rising = resolve_effective_target(_snap(indoor_temp=25.0), _mem(0.6), {}, _opts())
    assert rising.cooling_drop > calm.cooling_drop


def test_open_cool_window_relaxes_setpoint():
    r = resolve_effective_target(_snap(indoor_temp=22.0, window_open=True, outdoor_temp=15.0), _mem(), {}, _opts())
    assert r.effective_target > 22
    assert r.relaxation > 0


def test_clamped_to_device_min():
    r = resolve_effective_target(_snap(indoor_temp=30.0, min_temp=21.0), _mem(), {}, _opts())
    assert r.effective_target == 21
    assert r.limited_by_min is True


def test_effective_target_flows_into_cooling():
    caps = Capabilities(climate=True, temperature=True, humidity=False, weather=False, occupancy=False,
                        windows=False, pricing=False, air_quality=False, blinds=False, illuminance=False,
                        fan=False, purifier=False, humidifier=False, ionizer=False, ventilation=False, smoke=False, lightning=False, outlet_overload=False)
    ev = {
        "thermal": _Thermal(0.6), "humidity": _Hum(), "mold": _Mold(),
        "target": TargetResult(base_target=22, effective_target=19, reason="hot"),
    }
    hvac, target, driver = resolve_climate(_snap(indoor_temp=28.0), caps, _opts(), ev, passive_cooling=False)
    assert hvac == HVAC_COOL
    assert target == 19  # the effective target, not the static baseline of 22


class _Thermal:
    def __init__(self, c):
        self.confidence = c
        self.reason = "t"


class _Hum:
    confidence = 0.0


class _Mold:
    risk = 0.0
    airflow_recommended = False


class _Energy:
    def __init__(self, penalty, expensive):
        self.penalty = penalty
        self.expensive = expensive


def test_night_relaxes_setpoint_automatically():
    day = resolve_effective_target(_snap(indoor_temp=22.0, sun_up=True), _mem(), {}, _opts())
    night = resolve_effective_target(_snap(indoor_temp=22.0, sun_up=False), _mem(), {}, _opts())
    assert night.effective_target > day.effective_target  # sleep-like, no mode needed


def test_expensive_energy_relaxes_setpoint_automatically():
    cheap = resolve_effective_target(_snap(indoor_temp=22.0), _mem(), {"energy": _Energy(0.0, False)}, _opts())
    pricey = resolve_effective_target(_snap(indoor_temp=22.0), _mem(), {"energy": _Energy(0.3, True)}, _opts())
    assert pricey.effective_target > cheap.effective_target  # eco, no mode needed
    assert "energy price" in pricey.reason


def test_hot_outdoor_deepens_setpoint_preemptively():
    mild = resolve_effective_target(_snap(indoor_temp=22.0, outdoor_temp=18.0), _mem(), {}, _opts())
    hot_out = resolve_effective_target(_snap(indoor_temp=22.0, outdoor_temp=33.0), _mem(), {}, _opts())
    assert hot_out.effective_target < mild.effective_target


def test_forecast_precools_when_power_is_cheap():
    snap = _snap(indoor_temp=22.0, outdoor_temp=18.0, forecast_high=30.0, forecast_pressure=0.8, price_precool=True)
    r = resolve_effective_target(snap, _mem(), {"energy": _Energy(0.0, False)}, _opts())
    assert r.precool > 0
    assert r.effective_target < 22
    assert "pre-cooling" in r.reason


def test_forecast_precool_suppressed_when_power_expensive():
    snap = _snap(indoor_temp=22.0, outdoor_temp=18.0, forecast_high=30.0)
    r = resolve_effective_target(snap, _mem(), {"energy": _Energy(0.3, True)}, _opts())
    assert r.precool == 0  # don't bank coolth during an expensive window


def test_no_forecast_sensor_means_no_precool():
    r = resolve_effective_target(_snap(indoor_temp=22.0, outdoor_temp=18.0), _mem(), {}, _opts())
    assert r.precool == 0


def _opts_hum(comfort=60, cooling=1.0):
    return make_options(humidity_comfort=comfort, humidity_cooling=cooling)


def test_price_barely_above_average_does_not_relax():
    # penalty > 0 but not "expensive" (ratio < 1.25) -> no eco relaxation, no noise
    r = resolve_effective_target(_snap(indoor_temp=22.0), _mem(), {"energy": _Energy(0.05, False)}, _opts())
    assert r.relaxation == 0
    assert r.effective_target == 22



def test_dew_point_floor_prevents_condensation():
    from custom_components.environment_engine.psychrometrics import dew_point
    r = resolve_effective_target(_snap(indoor_temp=27.0, humidity=85.0), _mem(), {}, _opts())
    floor = dew_point(27.0, 85.0) + 2.0
    assert r.effective_target >= int(round(floor)) - 1
    assert "dew point" in r.reason


def test_dry_room_is_unaffected_by_dew_guard():
    r = resolve_effective_target(_snap(indoor_temp=28.0, humidity=40.0), _mem(), {}, _opts())
    assert "dew point" not in r.reason


class _AQSeal:
    def __init__(self, seal): self.seal = seal


def test_seal_suppresses_ventilation_relaxation():
    room = _snap(indoor_temp=22.0, humidity=50.0, window_open=True, outdoor_temp=15.0)
    normal = resolve_effective_target(room, _mem(), {"air_quality": _AQSeal(False)}, _opts())
    sealed = resolve_effective_target(room, _mem(), {"air_quality": _AQSeal(True)}, _opts())
    assert normal.effective_target > 22    # open cool window relaxes the setpoint
    assert sealed.effective_target <= 22   # sealed: no ventilation relaxation


def test_dark_night_relaxes_more_than_lit_night():
    lit = resolve_effective_target(_snap(indoor_temp=22.0, sun_up=False, dark=False), _mem(), {}, _opts())
    sleep = resolve_effective_target(_snap(indoor_temp=22.0, sun_up=False, dark=True), _mem(), {}, _opts())
    assert sleep.effective_target > lit.effective_target
    assert "sleep" in sleep.reason


def test_no_precool_outside_cheapest_window():
    snap = _snap(indoor_temp=22.0, forecast_pressure=0.8, price_precool=False)
    r = resolve_effective_target(snap, _mem(), {"energy": _Energy(0.3, True)}, _opts())
    assert r.precool == 0

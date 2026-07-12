"""Quiet hours: hold the compressor back and move air instead -- unless it's too hot."""
from datetime import time
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.const import HVAC_COOL, HVAC_FAN_ONLY, STRATEGY_QUIET_COOLING
from custom_components.environment_engine.quiet_hours import in_quiet_hours, parse_time
from custom_components.environment_engine.resolvers import resolve_climate
from custom_components.environment_engine.snapshot import Snapshot


def test_window_wraps_midnight():
    assert in_quiet_hours(time(23, 0), "22:00", "07:00") is True
    assert in_quiet_hours(time(3, 0), "22:00", "07:00") is True
    assert in_quiet_hours(time(12, 0), "22:00", "07:00") is False


def test_daytime_window_does_not_wrap():
    assert in_quiet_hours(time(14, 0), "13:00", "16:00") is True
    assert in_quiet_hours(time(17, 0), "13:00", "16:00") is False


def test_empty_window_is_never_quiet():
    assert in_quiet_hours(time(12, 0), "22:00", "22:00") is False


def test_bad_time_is_never_quiet():
    assert in_quiet_hours(time(12, 0), "nonsense", "07:00") is False
    assert parse_time("25:00") is None


def _caps(fan=True):
    return Capabilities(climate=True, temperature=True, humidity=False, weather=False, occupancy=False,
                        windows=False, pricing=False, air_quality=False, blinds=False, illuminance=False,
                        fan=fan, purifier=False, humidifier=False, ionizer=False, ventilation=False,
                        smoke=False, lightning=False, outlet_overload=False)


def _snap(feels, quiet):
    return Snapshot(indoor_temp=feels, humidity=50.0, feels_like=feels, outdoor_temp=20.0, occupancy=True,
                    window_open=False, energy_price=None, co2=None, voc=None, hvac_mode="off",
                    hvac_modes=["off", "cool", "dry", "fan_only"], min_temp=16.0, max_temp=30.0,
                    climate_valid=True, quiet=quiet)


class _T:
    def __init__(self, c): self.confidence = c


class _M:
    risk = 0.0
    airflow_recommended = False
    confidence = 0.0


class _H:
    confidence = 0.0


class _Tgt:
    effective_target = 22


def _ev(c=0.6):
    return {"thermal": _T(c), "mold": _M(), "humidity": _H(), "target": _Tgt()}


def test_quiet_hours_fan_only_instead_of_cooling():
    opts = make_options(quiet_hours=True, quiet_max_temp=26.0)
    mode, _, driver = resolve_climate(_snap(24.0, quiet=True), _caps(), opts, _ev(), False)
    assert mode == HVAC_FAN_ONLY  # compressor held back
    assert driver == STRATEGY_QUIET_COOLING


def test_ac_may_fan_during_quiet_even_with_a_standalone_fan():
    opts = make_options(quiet_hours=True, quiet_max_temp=26.0)
    mode, _, _ = resolve_climate(_snap(24.0, quiet=True), _caps(fan=True), opts, _ev(), False)
    assert mode == HVAC_FAN_ONLY  # the whole point: the AC's own fan_only gets used


def test_too_hot_overrides_quiet_and_cools():
    opts = make_options(quiet_hours=True, quiet_max_temp=26.0)
    mode, _, _ = resolve_climate(_snap(27.0, quiet=True), _caps(), opts, _ev(), False)
    assert mode == HVAC_COOL  # comfort wins; quiet hours never let the room cook


def test_outside_quiet_hours_cools_normally():
    opts = make_options(quiet_hours=True, quiet_max_temp=26.0)
    mode, _, _ = resolve_climate(_snap(24.0, quiet=False), _caps(), opts, _ev(), False)
    assert mode == HVAC_COOL

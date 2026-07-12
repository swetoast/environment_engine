"""Feels-like (heat-index) temperature and its effect on the thermal read."""
from custom_components.environment_engine.psychrometrics import feels_like
from custom_components.environment_engine.evaluators import evaluate_thermal
from custom_components.environment_engine.snapshot import Snapshot


def test_dry_warm_unchanged():
    assert feels_like(26.0, 40.0, 1.5) == 26.0


def test_muggy_warm_feels_hotter():
    assert feels_like(26.0, 85.0, 1.5) > 26.5


def test_cool_room_unchanged():
    assert feels_like(18.0, 90.0, 1.5) == 18.0


def test_bump_capped():
    assert feels_like(35.0, 100.0, 1.0) <= 36.0  # never exceeds temp + cap


def test_zero_cap_disables():
    assert feels_like(30.0, 90.0, 0.0) == 30.0


def test_missing_humidity_returns_drybulb():
    assert feels_like(28.0, None, 1.5) == 28.0


class _Mem:
    thermal_inertia = 0.0
    temperature_trend = 0.0


def _snap(indoor, feels):
    return Snapshot(indoor_temp=indoor, humidity=60.0, outdoor_temp=20.0, occupancy=True, window_open=False,
                    energy_price=None, co2=None, voc=None, hvac_mode="off", feels_like=feels)


def test_thermal_uses_feels_like():
    dry = evaluate_thermal(_snap(25.0, 25.0), _Mem(), 0.0, 0.0, target=22.0)
    muggy = evaluate_thermal(_snap(25.0, 27.0), _Mem(), 0.0, 0.0, target=22.0)
    assert muggy.confidence > dry.confidence  # same air temp, feels warmer -> cools sooner


def test_thermal_falls_back_to_drybulb_when_no_feels_like():
    r = evaluate_thermal(_snap(26.0, None), _Mem(), 0.0, 0.0, target=22.0)
    assert r.pressure > 0

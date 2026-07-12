"""Relative energy pricing: expensive is defined vs today's average, with a
fixed-threshold fallback when no average sensor is configured."""
from _helpers import make_options
from custom_components.environment_engine.evaluators import evaluate_energy
from custom_components.environment_engine.snapshot import Snapshot


def _opts():
    return make_options()


def _snap(price=None, average=None):
    return Snapshot(indoor_temp=22.0, humidity=50.0, outdoor_temp=18.0, occupancy=True, window_open=False,
                    energy_price=price, co2=None, voc=None, hvac_mode="off", price_average=average)


# real SE3 spot for the day: avg 0.6255, now 0.8358, high 1.1164, low 0.1527
def test_above_average_is_expensive():
    r = evaluate_energy(_snap(price=0.8358, average=0.6255), _opts())
    assert r.expensive is True
    assert r.penalty > 0
    assert "above today's average" in r.reason


def test_daily_peak_hits_penalty_cap():
    r = evaluate_energy(_snap(price=1.1164, average=0.6255), _opts())
    assert r.penalty == 0.3  # capped
    assert r.expensive is True


def test_cheap_slot_is_not_expensive_and_no_penalty():
    r = evaluate_energy(_snap(price=0.1527, average=0.6255), _opts())
    assert r.expensive is False
    assert r.penalty == 0.0
    assert "below" in r.reason


def test_near_average_is_neutral():
    r = evaluate_energy(_snap(price=0.63, average=0.6255), _opts())
    assert r.expensive is False
    assert "near" in r.reason


def test_falls_back_to_fixed_threshold_without_average():
    # no average sensor -> fixed price_high (3.0) comparison
    cheap = evaluate_energy(_snap(price=0.85), _opts())
    assert cheap.expensive is False  # 0.85 well under 3.0
    pricey = evaluate_energy(_snap(price=2.9), _opts())
    assert pricey.expensive is True


def test_no_price_is_unavailable():
    r = evaluate_energy(_snap(), _opts())
    assert r.penalty == 0.0 and r.expensive is False

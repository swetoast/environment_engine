"""The learned air model: measured purifier performance, not an hours guess."""
import random
from custom_components.environment_engine.air_model import AirModel, speed_fraction

TRUE_CADR, TRUE_DEP, TRUE_INF, TRUE_GEN = 0.060, 0.010, 0.020, 0.35


class _A:
    def __init__(self, pm, outdoor, window_open=False):
        self.pm25 = pm
        self.pm10 = None
        self.outdoor_aqi = outdoor
        self.window_open = window_open


def _run(cadr=TRUE_CADR, n=600, seed=2, model=None):
    random.seed(seed)
    m = model or AirModel()
    pm = 20.0
    for _ in range(n):
        outdoor = 15 + 10 * random.random()
        speed = 1.0 if pm > 25 else (0.33 if pm > 12 else 0.0)
        prev = _A(pm, outdoor)
        drift = -cadr * speed * pm - TRUE_DEP * pm + TRUE_INF * outdoor + TRUE_GEN + random.gauss(0, 0.05)
        pm = max(0.5, pm + drift * 5)
        m.update(prev, _A(pm, outdoor), 5.0, speed)
    return m


def test_measures_the_purifiers_actual_clean_rate():
    m = _run()
    assert abs(m.clean_rate - TRUE_CADR) < 0.01
    assert m.confidence > 0.8


def test_learns_how_leaky_the_flat_is_to_outdoor_air():
    m = _run()
    assert abs(m.infiltration - TRUE_INF) < 0.015


def test_a_clogged_filter_is_measured_not_guessed():
    fresh = _run()                                   # a good filter sets the benchmark
    assert fresh.filter_health > 0.9
    clogged = AirModel()
    clogged.restore(fresh.as_dict())                 # same unit, peak_cadr remembered
    _run(cadr=TRUE_CADR * 0.4, seed=9, model=clogged)   # filter now removes 40% as much
    health = clogged.filter_health
    assert health is not None and 0.3 < health < 0.55  # ~40%, whatever the hours counter says


def test_no_accusation_without_evidence():
    assert AirModel().filter_health is None          # a cold model never blames your filter


def test_minutes_to_clear():
    m = _run()
    assert m.minutes_to_clear(60.0, 12.0) > 0
    assert m.minutes_to_clear(10.0, 12.0) is None    # already clean


def test_dirty_samples_rejected():
    m = AirModel()
    assert m.update(_A(20, 10, window_open=True), _A(25, 10, window_open=True), 5.0, 1.0) is False
    assert m.update(_A(None, 10), _A(20, 10), 5.0, 1.0) is False
    assert m.update(_A(20, 10), _A(400, 10), 5.0, 1.0) is False   # sensor spike
    assert m.update(_A(20, 10), _A(25, 10), 900.0, 1.0) is False  # restart gap
    assert m.samples == 0 and m.rejected == 4


def test_speed_fraction_maps_engine_actions():
    assert speed_fraction("off", None) == 0.0
    assert speed_fraction(None, "high") == 0.0
    assert speed_fraction("on", "low") < speed_fraction("on", "high")


def test_persistence_round_trip_and_safe_restore():
    m = _run()
    other = AirModel()
    assert other.restore(m.as_dict()) is True
    assert abs(other.clean_rate - m.clean_rate) < 1e-9
    assert other.peak_cadr == m.peak_cadr
    assert AirModel().restore({"theta": [1, 2]}) is False
    assert AirModel().restore(None) is False

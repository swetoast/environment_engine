"""The learned thermal model: does it recover real physics, and stay honest when it can't?"""
import random
from custom_components.environment_engine.thermal_model import BucketedRates, ThermalModel

TRUE_K, TRUE_S, TRUE_C, TRUE_B = 0.006, 0.15, -0.08, 0.004


class _S:
    def __init__(self, indoor, outdoor, sun_up=True, window_open=False, hvac_mode="off",
                 occupancy=False, temperature_valid=True):
        self.indoor_temp = indoor
        self.outdoor_temp = outdoor
        self.sun_up = sun_up
        self.window_open = window_open
        self.hvac_mode = hvac_mode
        self.occupancy = occupancy
        self.temperature_valid = temperature_valid


def _true_drift(tin, tout, solar, cooling):
    return TRUE_K * (tout - tin) + TRUE_S * solar + (TRUE_C if cooling else 0.0) + TRUE_B


def _train(days=3, seed=7):
    random.seed(seed)
    model, indoor, dt = ThermalModel(), 22.0, 5.0
    for step in range(days * 24 * 12):
        hour = (step * 5 / 60) % 24
        sun_up = 6 <= hour <= 21
        solar = max(0.0, 1 - abs(hour - 14) / 8) if sun_up else 0.0
        outdoor = 18 + 9 * max(0.0, 1 - abs(hour - 15) / 9)
        cooling = indoor > 24.5
        mode = "cool" if cooling else "off"
        prev = _S(indoor, outdoor, sun_up, hvac_mode=mode)
        indoor += (_true_drift(indoor, outdoor, solar, cooling) + random.gauss(0, 0.002)) * dt
        model.update(prev, _S(indoor, outdoor, sun_up, hvac_mode=mode), dt, cooling, solar)
    return model


def test_recovers_the_rooms_physics():
    m = _train()
    assert abs(m.leakiness - TRUE_K) < 0.002
    assert abs(m.solar_gain - TRUE_S) < 0.05
    assert abs(m.cooling_power - TRUE_C) < 0.02
    assert m.confidence > 0.8


def test_time_constant_is_plausible():
    tau = _train().time_constant
    assert 60 < tau < 400  # a room, not a thermos and not a tent


def test_prediction_tracks_reality():
    m = _train()
    predicted = m.predict(25.0, 27.0, solar=0.9, minutes=30)
    truth = 25.0
    for _ in range(6):
        truth += _true_drift(truth, 27.0, 0.9, False) * 5
    assert abs(predicted - truth) < 0.3


def test_cold_start_is_honest():
    m = ThermalModel()
    assert m.confidence == 0.0
    assert m.predict(25.0, 30.0, 0.5, 30) is None      # refuses to guess
    assert m.anticipation(25.0, 30.0) == 0.0            # stays reactive


def test_dirty_samples_are_rejected():
    m = ThermalModel()
    open_window = (_S(24.0, 30.0, window_open=True), _S(25.0, 30.0, window_open=True))
    assert m.update(*open_window, 5.0, False, 0.5) is False
    mode_flip = (_S(24.0, 30.0, hvac_mode="off"), _S(25.0, 30.0, hvac_mode="cool"))
    assert m.update(*mode_flip, 5.0, False, 0.5) is False
    long_gap = (_S(24.0, 30.0), _S(25.0, 30.0))
    assert m.update(*long_gap, 600.0, False, 0.5) is False   # restart, not physics
    glitch = (_S(24.0, 30.0), _S(40.0, 30.0))
    assert m.update(*glitch, 5.0, False, 0.5) is False        # sensor spike
    assert m.samples == 0 and m.rejected == 4


def test_coefficients_are_physically_bounded():
    m = ThermalModel()
    m.theta = [99.0, 99.0, 99.0, 99.0]   # a wild fit must not produce wild control
    assert 0.0 <= m.leakiness <= 0.05
    assert m.cooling_power <= 0.0


def test_struggling_flag_when_cooling_loses():
    m = ThermalModel()
    prev, cur = _S(28.0, 38.0, hvac_mode="cool"), _S(28.3, 38.0, hvac_mode="cool")
    m.update(prev, cur, 5.0, True, 1.0)   # compressor on, room still gaining
    assert m.struggling is True


def test_cooling_effectiveness_is_bucketed_by_outdoor_temp():
    m = _train()
    assert m.cooling_effect  # learned how much it can actually remove
    assert all(v >= 0 for v in m.cooling_effect.values())


def test_bucketed_rates_work_from_day_one():
    b = BucketedRates()
    key = b.key(sun_up=True, outdoor_warmer=True)
    for _ in range(6):
        b.update(key, 0.02)
    assert b.samples(key) == 6
    assert abs(b.rate(key) - 0.02) < 0.005


def test_falls_back_to_buckets_before_the_model_is_trusted():
    m = ThermalModel()
    key = m.buckets.key(True, True)
    for _ in range(6):
        m.buckets.update(key, 0.02)          # 0.02 C/min observed in these conditions
    assert m.confidence == 0.0               # model not trusted yet
    assert m.anticipation(24.0, 30.0, sun_up=True) > 0.0   # but it still anticipates


def test_cooling_bias_rewards_an_effective_unit():
    m = _train()                       # a healthy AC (true c = -0.08)
    assert m.effectiveness > 0.8
    assert m.cooling_bias() > 0.0      # cooling works here -> lean into it


def test_cooling_bias_is_negative_for_a_feeble_unit():
    m = _train()
    m.theta[2] = -0.005                # barely removes any heat
    assert m.effectiveness < 0.2
    assert m.cooling_bias() < 0.0      # don't spend energy for nothing


def test_cooling_bias_is_bounded_and_silent_when_unlearned():
    assert ThermalModel().cooling_bias() == 0.0        # no evidence -> no opinion
    m = _train()
    assert -0.05 <= m.cooling_bias() <= 0.05           # never more than a nudge


def test_struggling_does_not_reduce_willingness_to_cool():
    # A room the AC is losing to is the room that needs cooling most. Struggling must be
    # a diagnostic, never a reason to back off.
    m = _train()
    before = m.cooling_bias()
    m.struggling = True
    assert m.cooling_bias() == before


def test_a_dead_temperature_sensor_does_not_poison_the_model():
    """Regression: a dropped sensor reports a substituted 0 °C. Sample-to-sample that looks
    perfectly calm -- no spike, sane timing -- so the model happily learned that the room
    sits at 0 °C and never moves, wrecking the fitted leakiness. The validity flag must
    reject those samples."""
    class _Dead:
        indoor_temp = 0.0
        outdoor_temp = 25.0
        sun_up = True
        window_open = False
        hvac_mode = "off"
        temperature_valid = False

    m = ThermalModel()
    for _ in range(20):
        assert m.update(_Dead(), _Dead(), 5.0, False, 0.5) is False
    assert m.samples == 0 and m.rejected == 20


def test_model_survives_a_missing_outdoor_sensor():
    m = ThermalModel()
    assert m.drift(24.0, None, 0.0) == 0.0        # nothing to model with -> no drift
    assert m.predict(24.0, None, 0.0, 30) is None
    assert m.anticipation(24.0, None) == 0.0
    assert ThermalModel.outdoor_band(None) == "unknown"


TRUE_O = 0.030  # the heat you add just by being home


def _train_with_occupancy(days=4, seed=11):
    """Away at work 08:00-17:00 -- an empty house is the cleanest laboratory there is."""
    random.seed(seed)
    model, indoor, dt = ThermalModel(), 22.0, 5.0
    for step in range(days * 24 * 12):
        hour = (step * 5 / 60) % 24
        sun_up = 6 <= hour <= 21
        solar = max(0.0, 1 - abs(hour - 14) / 8) if sun_up else 0.0
        outdoor = 18 + 9 * max(0.0, 1 - abs(hour - 15) / 9)
        cooling = indoor > 24.5
        mode = "cool" if cooling else "off"
        occupied = not (8 <= hour < 17)
        prev = _S(indoor, outdoor, sun_up, hvac_mode=mode, occupancy=occupied)
        drift = (_true_drift(indoor, outdoor, solar, cooling)
                 + (TRUE_O if occupied else 0.0) + random.gauss(0, 0.002))
        indoor += drift * dt
        model.update(prev, _S(indoor, outdoor, sun_up, hvac_mode=mode, occupancy=occupied), dt, cooling, solar)
    return model


def test_learns_the_heat_you_add_by_being_home():
    m = _train_with_occupancy()
    assert abs(m.occupied_gain - TRUE_O) < 0.01
    # and it doesn't smear that into the base physics
    assert abs(m.leakiness - TRUE_K) < 0.002
    assert abs(m.internal_gain - TRUE_B) < 0.01


def test_predictions_differ_between_home_and_away():
    m = _train_with_occupancy()
    home = m.predict(24.0, 28.0, solar=0.8, minutes=60, occupied=True)
    away = m.predict(24.0, 28.0, solar=0.8, minutes=60, occupied=False)
    assert home > away + 0.5   # an occupied room heats up meaningfully faster


def test_occupancy_change_mid_interval_is_rejected():
    m = ThermalModel()
    came_home = (_S(24.0, 30.0, occupancy=False), _S(24.5, 30.0, occupancy=True))
    assert m.update(*came_home, 5.0, False, 0.5) is False
    assert m.samples == 0


def test_it_keeps_learning_while_you_are_away():
    m = ThermalModel()
    empty = (_S(24.0, 30.0, occupancy=False), _S(24.2, 30.0, occupancy=False))
    assert m.update(*empty, 5.0, False, 0.5) is True   # an empty house is the best data


def test_persistence_round_trip():
    m = _train_with_occupancy()
    restored = ThermalModel()
    assert restored.restore(m.as_dict()) is True
    assert abs(restored.leakiness - m.leakiness) < 1e-9
    assert restored.samples == m.samples
    assert restored.confidence == m.confidence
    assert restored.buckets.rates == m.buckets.rates


def test_persisted_state_is_small_and_bounded():
    import json
    m = _train_with_occupancy()
    blob = json.dumps(m.as_dict())
    assert len(blob) < 3000  # lessons only -- no sample history, so it never grows


def test_a_bad_restore_is_never_fatal():
    assert ThermalModel().restore(None) is False
    assert ThermalModel().restore({}) is False
    assert ThermalModel().restore({"theta": [1, 2]}) is False
    assert ThermalModel().restore({"theta": "nonsense", "p": []}) is False
    # a model saved by an older version with fewer coefficients -> start clean, don't crash
    assert ThermalModel().restore({"theta": [0.0] * 4, "p": [[1.0] * 4] * 4}) is False


def _step(m, state, hour, extra=0.0):
    indoor = state["indoor"]
    sun_up = 6 <= hour <= 21
    solar = max(0.0, 1 - abs(hour - 14) / 8) if sun_up else 0.0
    outdoor = 18 + 9 * max(0.0, 1 - abs(hour - 15) / 9)
    cooling = indoor > 24.5
    mode = "cool" if cooling else "off"
    prev = _S(indoor, outdoor, sun_up, hvac_mode=mode, occupancy=True)
    drift = (_true_drift(indoor, outdoor, solar, cooling) + TRUE_O + extra + random.gauss(0, 0.002))
    indoor += drift * 5
    m.update(prev, _S(indoor, outdoor, sun_up, hvac_mode=mode, occupancy=True), 5.0, cooling, solar)
    state["indoor"] = indoor


def test_anomaly_is_quiet_when_the_physics_explains_everything():
    random.seed(4)
    m, state = ThermalModel(), {"indoor": 22.0}
    for i in range(3 * 24 * 12):
        _step(m, state, (i * 5 / 60) % 24)
    assert m.anomaly() is None
    assert m.anomaly_score < 2.0


def test_anomaly_catches_a_door_left_open():
    """A persistent one-sided error the model can't explain -- a window cracked, an oven on,
    a radiator that came back, or a sensor drifting."""
    random.seed(4)
    m, state = ThermalModel(), {"indoor": 22.0}
    for i in range(3 * 24 * 12):
        _step(m, state, (i * 5 / 60) % 24)
    for _ in range(12):                       # one hour of unexplained heat gain
        _step(m, state, 14.0, extra=0.05)
    assert m.anomaly() == "heating"
    assert m.anomaly_score > 2.0
    assert m.unexplained_drift > 0


def test_anomaly_recovers_once_the_cause_is_gone():
    random.seed(4)
    m, state = ThermalModel(), {"indoor": 22.0}
    for i in range(3 * 24 * 12):
        _step(m, state, (i * 5 / 60) % 24)
    for _ in range(12):
        _step(m, state, 14.0, extra=0.05)
    assert m.anomaly() == "heating"
    for _ in range(36):                       # door closed again
        _step(m, state, 15.0)
    assert m.anomaly() is None


def test_an_unlearned_model_never_accuses():
    assert ThermalModel().anomaly() is None
    assert ThermalModel().anomaly_score == 0.0
    assert ThermalModel().unexplained_drift == 0.0

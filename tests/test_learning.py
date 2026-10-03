"""What the engine learns about a room, and that it stays honest about it.

The models are fed synthetic rooms with KNOWN physics, so each test can check the fit
against the truth: the thermal model, the air model behind the filter reminder, the
short-term trend memory, and persistence across a restart.
"""
import random

from custom_components.environment_engine.air_model import AirModel
from custom_components.environment_engine.thermal_memory import ThermalMemoryEngine
from custom_components.environment_engine.thermal_model import ThermalModel
from harness import Clock, Home

LEAK, SUN, COOLING, INTERNAL = 0.006, 0.15, -0.08, 0.004          # °C per minute terms
CADR, DEPOSITION, INFILTRATION, GENERATION = 0.060, 0.010, 0.020, 0.35


class _Room:
    def __init__(self, indoor, outdoor, sun_up=True, window_open=False, hvac_mode="off", occupancy=False,
                 temperature_valid=True):
        self.indoor_temp, self.outdoor_temp, self.sun_up = indoor, outdoor, sun_up
        self.window_open, self.hvac_mode, self.occupancy = window_open, hvac_mode, occupancy
        self.temperature_valid = temperature_valid


class _Air:
    def __init__(self, pm25, outdoor_aqi, window_open=False):
        self.pm25, self.pm10, self.outdoor_aqi, self.window_open = pm25, None, outdoor_aqi, window_open


def _drift(indoor, outdoor, solar, cooling):
    return LEAK * (outdoor - indoor) + SUN * solar + (COOLING if cooling else 0.0) + INTERNAL


def _trained_thermal(days=3):
    rng = random.Random(7)
    model, indoor, dt = ThermalModel(), 22.0, 5.0
    for step in range(days * 24 * 12):
        hour = (step * 5 / 60) % 24
        sun_up = 6 <= hour <= 21
        solar = max(0.0, 1 - abs(hour - 14) / 8) if sun_up else 0.0
        outdoor = 18 + 9 * max(0.0, 1 - abs(hour - 15) / 9)
        cooling = indoor > 24.5
        mode = "cool" if cooling else "off"
        before = _Room(indoor, outdoor, sun_up, hvac_mode=mode)
        indoor += (_drift(indoor, outdoor, solar, cooling) + rng.gauss(0, 0.002)) * dt
        model.update(before, _Room(indoor, outdoor, sun_up, hvac_mode=mode), dt, cooling, solar)
    return model


def _trained_air(cadr=CADR, model=None, seed=2):
    rng = random.Random(seed)
    model, pm = model or AirModel(), 20.0
    for _ in range(600):
        outdoor = 15 + 10 * rng.random()
        speed = 1.0 if pm > 25 else (0.33 if pm > 12 else 0.0)
        before = _Air(pm, outdoor)
        pm = max(0.5, pm + (-cadr * speed * pm - DEPOSITION * pm + INFILTRATION * outdoor + GENERATION + rng.gauss(0, 0.05)) * 5)
        model.update(before, _Air(pm, outdoor), 5.0, speed)
    return model


def test_thermal_model_recovers_the_rooms_physics_and_predicts_with_it():
    model = _trained_thermal()
    assert abs(model.leakiness - LEAK) < 0.002
    assert abs(model.solar_gain - SUN) < 0.05
    assert abs(model.cooling_power - COOLING) < 0.02
    assert model.confidence > 0.8 and 60 < model.time_constant < 400
    truth = 25.0
    for _ in range(6):
        truth += _drift(truth, 27.0, 0.9, False) * 5
    assert abs(model.predict(25.0, 27.0, solar=0.9, minutes=30) - truth) < 0.3
    assert model.anticipation(25.0, 30.0, solar=0.9, sun_up=True, occupied=False) > 0
    assert 0.8 <= model.effectiveness <= 1.0 and not model.struggling      # measured against its own best


def test_thermal_model_refuses_to_guess_and_rejects_dirty_samples():
    model = ThermalModel()
    assert model.confidence == 0.0 and model.predict(25.0, 30.0, 0.5, 30) is None and model.anticipation(25.0, 30.0) == 0.0
    dirty = [
        (_Room(24.0, 30.0, window_open=True), _Room(25.0, 30.0, window_open=True), 5.0),      # open window
        (_Room(24.0, 30.0, hvac_mode="off"), _Room(25.0, 30.0, hvac_mode="cool"), 5.0),      # mode changed mid-interval
        (_Room(24.0, 30.0), _Room(25.0, 30.0), 600.0),                                        # restart gap
        (_Room(24.0, 30.0), _Room(40.0, 30.0), 5.0),                                          # sensor spike
        (_Room(0.0, 30.0, temperature_valid=False), _Room(0.0, 30.0, temperature_valid=False), 5.0),  # dead sensor
        (_Room(24.0, 30.0, occupancy=False), _Room(24.1, 30.0, occupancy=True), 5.0),        # someone arrived
    ]
    for before, after, dt in dirty:
        assert model.update(before, after, dt, False, 0.5) is False
    assert model.samples == 0 and model.rejected == len(dirty)
    # A wild fit cannot produce wild control: coefficients are clamped to what a room can do.
    model.theta = [99.0, 99.0, 99.0, 99.0, 99.0]
    assert 0.0 <= model.leakiness <= 0.05 and model.cooling_power <= 0.0
    # Compressor running and the room still gaining heat is flagged.
    model = ThermalModel()
    model.update(_Room(28.0, 38.0, hvac_mode="cool"), _Room(28.3, 38.0, hvac_mode="cool"), 5.0, True, 1.0)
    assert model.struggling is True


def test_air_model_measures_the_purifier_and_notices_a_clogged_filter():
    fresh = _trained_air()
    assert abs(fresh.clean_rate - CADR) < 0.01 and abs(fresh.infiltration - INFILTRATION) < 0.015
    assert fresh.confidence > 0.8 and fresh.filter_health > 0.9
    assert fresh.minutes_to_clear(60.0, 12.0) > 0
    assert AirModel().filter_health is None                               # no evidence, no accusation
    clogged = AirModel()
    clogged.restore(fresh.as_dict())                                      # same unit, its best remembered
    _trained_air(cadr=CADR * 0.4, model=clogged, seed=9)
    assert 0.3 < clogged.filter_health < 0.55                             # about 40 %, whatever the hours say
    blank = AirModel()
    for before, after, dt in [(_Air(20, 10, True), _Air(25, 10, True), 5.0), (_Air(None, 10), _Air(20, 10), 5.0),
                              (_Air(20, 10), _Air(400, 10), 5.0), (_Air(20, 10), _Air(25, 10), 900.0)]:
        assert blank.update(before, after, dt, 1.0) is False
    assert blank.samples == 0


def test_trend_memory_ignores_noise_dropouts_and_gaps_and_is_per_minute():
    rng = random.Random(1)
    noisy = ThermalMemoryEngine()
    peak = 0.0
    for _ in range(300):
        noisy.update(22.0 + rng.uniform(-0.05, 0.05), 50.0, 20.0, True, 1.0)
        peak = max(peak, abs(noisy.memory.temperature_trend))
    assert peak < 0.025                                                    # sensor noise is not a trend

    warming = ThermalMemoryEngine()
    for step in range(10):
        warming.update(22.0 + 0.05 * step, 50.0, 20.0, True, 1.0)         # 3 °C per hour
    assert warming.memory.temperature_trend > 0.025

    dropout = ThermalMemoryEngine()
    dropout.update(22.0, 50.0, 20.0, True, 1.0)
    dropout.update(0.0, 50.0, 20.0, False, 1.0)                           # placeholder reading
    dropout.update(22.0, 80.0, 20.0, True, 600.0)                         # back after a long gap
    assert dropout.memory.temperature_trend == 0.0 and dropout.memory.humidity_trend == 0.0

    fast, slow = ThermalMemoryEngine(), ThermalMemoryEngine()
    fast.update(22.0, 50.0, 20.0, True, 1.0)
    slow.update(22.0, 50.0, 20.0, True, 10.0)
    for step in range(1, 61):                                             # humidity rising 0.2 % per minute
        fast.update(22.0, 50.0 + 0.2 * step, 20.0, True, 1.0)
        if step % 10 == 0:
            slow.update(22.0, 50.0 + 0.2 * step, 20.0, True, 10.0)
    assert abs(fast.memory.humidity_trend - 0.2) < 0.02 and abs(slow.memory.humidity_trend - 0.2) < 0.05


def test_learning_reads_the_devices_survives_a_restart_and_resets_on_request(monkeypatch):
    """Through the coordinator: the models are told what the devices actually did (not what
    the engine decided), their fit round-trips through storage, and Reset Learning clears it."""
    clock = Clock().install(monkeypatch)
    home = Home(temp=26.0, outdoor=30.0, ac=True, purifier=True, pm25=40, occupancy="on",
                options={"target_temperature": 22, "auto_apply": False})
    home.set("climate.ac", "cool")                                         # running, but not by the engine
    home.set("fan.purifier", "on", percentage=67)
    room, pm = 26.0, 40.0
    for _ in range(60):
        home.cycle(apply=False)
        clock.advance(60)
        room -= 0.05
        pm *= 0.97
        home.set("sensor.temp", f"{room:.2f}")
        home.set("sensor.pm25", f"{pm:.1f}")
    coordinator = home.coordinator
    snapshot = home.data_now["snapshot"]
    assert snapshot.compressor_running is True and abs(snapshot.purifier_level - 0.67) < 1e-9
    assert coordinator.thermal.samples > 50 and coordinator.thermal.cooling_effect      # booked as cooling
    assert coordinator.air.samples > 50 and coordinator.air.theta[0] > 0                # booked as purifying
    home.set("climate.ac", hvac_action="idle")                             # in cool mode but at its setpoint
    assert coordinator._snapshot().compressor_running is False

    saved = {"thermal": coordinator.thermal.as_dict(), "air": coordinator.air.as_dict()}
    restored_thermal, restored_air = ThermalModel(), AirModel()
    assert restored_thermal.restore(saved["thermal"]) and restored_air.restore(saved["air"])
    assert restored_thermal.samples == coordinator.thermal.samples and restored_air.theta == coordinator.air.theta
    assert ThermalModel().restore({"theta": "garbage"}) is False and AirModel().restore(None) is False

    coordinator.reset_learning()
    assert coordinator.thermal.samples == 0 and coordinator.air.samples == 0
    assert coordinator.learning.state.drying_successes == 0

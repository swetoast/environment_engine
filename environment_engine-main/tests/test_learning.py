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
    model.update(_Room(28.3, 38.0, hvac_mode="cool"), _Room(28.6, 38.0, hvac_mode="cool"), 5.0, True, 1.0)
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
    # Truly 40 %. A clogged filter keeps the purifier at full speed, which makes cleaning hard
    # to tell from natural settling, so the figure is approximate; the verdict is not.
    assert 0.15 < clogged.filter_health < 0.55
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
    for _ in range(240):
        home.cycle(apply=False)
        clock.advance(60)
        room -= 0.01
        pm = max(5.0, pm * 0.995)
        home.set("sensor.temp", f"{room:.2f}")
        home.set("sensor.pm25", f"{pm:.1f}")
    coordinator = home.coordinator
    snapshot = home.data_now["snapshot"]
    assert snapshot.compressor_running is True and abs(snapshot.purifier_level - 0.67) < 1e-9
    assert coordinator.thermal.samples >= 20 and coordinator.thermal.cooling_effect     # ten-minute windows, booked as cooling
    assert coordinator.air.samples >= 20 and coordinator.air.theta[0] > 0               # booked as purifying
    home.set("climate.ac", hvac_action="idle")                             # in cool mode but at its setpoint
    assert coordinator._snapshot().compressor_running is False

    coordinator.learning.state.drying_successes = 7
    coordinator._save_model()
    saved = coordinator._model_store.saved
    assert saved["drying"] == {"successes": 7, "failures": 0}             # the drying counter is persisted too
    restored_thermal, restored_air = ThermalModel(), AirModel()
    assert restored_thermal.restore(saved["thermal"]) and restored_air.restore(saved["air"])
    assert restored_thermal.samples == coordinator.thermal.samples and restored_air.theta == coordinator.air.theta
    assert ThermalModel().restore({"theta": "garbage"}) is False and AirModel().restore(None) is False

    coordinator.reset_learning()
    assert coordinator.thermal.samples == 0 and coordinator.air.samples == 0
    assert coordinator.learning.state.drying_successes == 0


def test_noisy_one_minute_readings_still_produce_a_trusted_model():
    """A 0.1 °C sensor read every minute: each reading is mostly rounding. Folded into
    ten-minute windows the fit still finds the room, and becomes trusted."""
    rng = random.Random(3)
    model, indoor = ThermalModel(), 22.0
    for minute in range(4 * 24 * 60):
        hour = (minute / 60) % 24
        outdoor = 20 + 8 * max(0.0, 1 - abs(hour - 15) / 9)
        cooling = indoor > 24.0
        before = _Room(round(indoor, 1), outdoor, hvac_mode="cool" if cooling else "off")
        indoor += _drift(indoor, outdoor, 0.0, cooling) + rng.gauss(0, 0.002)
        model.update(before, _Room(round(indoor, 1), outdoor, hvac_mode="cool" if cooling else "off"), 1.0, cooling, 0.0)
    assert model.confidence > 0.5
    assert abs(model.leakiness - LEAK) < 0.003 and abs(model.cooling_power - COOLING) < 0.03


def test_one_lucky_fit_does_not_become_the_benchmark():
    model = _trained_thermal()
    honest_peak = model.peak_effort
    model.theta[2] = -0.4                                                  # a single wild estimate
    model._rls([0.0, 0.0, 0.0, 0.0, 1.0], model.internal_gain)
    assert model.peak_effort < honest_peak * 1.5                           # the bar barely moves
    model.theta[2] = COOLING
    for _ in range(5):
        model._rls([0.0, 0.0, 0.0, 0.0, 1.0], model.internal_gain)
    assert model.effectiveness > 0.8                                       # and the unit is not "degraded" forever


def test_sun_gain_is_learned_by_hour_of_day():
    """A west-facing room: no sun gain at noon, a lot at 17:00. The sun-height proxy says
    the opposite, so the model has to learn the hours for itself."""
    rng = random.Random(5)
    model, indoor = ThermalModel(), 22.0
    for step in range(12 * 24 * 12):
        hour = (step * 5 / 60) % 24
        sun_up = 6 <= hour <= 21
        west = 0.02 * max(0.0, 1 - abs(hour - 17) / 3)                     # true gain, °C/min
        proxy = max(0.0, 1 - abs(hour - 12.5) / 8) if sun_up else 0.0       # what sun height suggests
        before = _Room(indoor, 20.0, sun_up)
        indoor += (LEAK * (20.0 - indoor) + west + INTERNAL + rng.gauss(0, 0.001)) * 5
        model.update(before, _Room(indoor, 20.0, sun_up), 5.0, False, proxy, hour=int(hour))
    assert model.sun_peak_hour in (16, 17, 18)
    assert model.learned_sun(17) > 3 * (model.learned_sun(11) or 0.0)
    assert model.drift(22.0, 20.0, 0.5, hour=17) > model.drift(22.0, 20.0, 0.5, hour=11)


def test_unit_sensor_offset_only_ever_lowers_the_sent_setpoint():
    cold = ThermalModel()                                                  # unit reads 2.4 below the room
    for _ in range(30):
        cold.observe_unit_sensor(-2.4, cooling=True)
    assert cold.setpoint_compensation == 2
    warm = ThermalModel()                                                  # unit reads 2.2 above the room
    for _ in range(30):
        warm.observe_unit_sensor(2.2, cooling=True)
    assert warm.setpoint_compensation == 0
    idle = ThermalModel()
    for _ in range(30):
        idle.observe_unit_sensor(-2.4, cooling=False)                      # only learned while cooling
    assert idle.setpoint_compensation == 0
    few = ThermalModel()
    few.observe_unit_sensor(-5.0, cooling=True)
    assert few.setpoint_compensation == 0                                  # not on one reading


def _teach(home, **overrides):
    """Hand the room's coordinator a trusted model of a known room."""
    model = _trained_thermal()
    for name, value in overrides.items():
        setattr(model, name, value)
    home.coordinator.thermal = model
    return model


def test_learning_drives_control_stop_gap_sensor_compensation_and_pre_cooling(monkeypatch):
    from datetime import datetime, timezone
    clock = Clock(datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)).install(monkeypatch)
    options = {"target_temperature": 22, "compressor_min_cycle": 300, "coil_dry_out": 0, "min_change_interval": 0}

    # Stop gap. Mild day, driven setpoint equals the user's. Untaught, a cycle stops at 22.0;
    # taught how fast the room rewarms, it runs a little under so the off-time covers a cycle.
    untaught = Home(temp=22.3, outdoor=24.0, ac=True, options=options)
    untaught.cycle()
    assert untaught.data_now["evaluations"]["target"].stop_at == 22.0
    home = Home(temp=22.3, outdoor=24.0, ac=True, options=options)
    _teach(home)
    home.cycle()
    target = home.data_now["evaluations"]["target"]
    gap = 22.0 - target.stop_at
    assert 0.0 < gap <= 1.0 and home.state("climate.ac") == "cool"
    assert abs(gap - home.data_now["snapshot"].rewarm_rate * 5) < 1e-6      # rewarm rate x a 5 minute cycle
    clock.advance(600)
    home.set("sensor.temp", 22.0 - gap / 2)
    home.cycle()
    assert home.state("climate.ac") == "cool"                              # under 22, still inside the gap
    clock.advance(600)
    home.set("sensor.temp", 22.0 - gap - 0.05)
    home.cycle()
    assert home.state("climate.ac") == "off"
    assert home.states["climate.ac"].attributes["temperature"] == 22       # the setpoint sent is still the user's

    # Sensor compensation. The unit's sensor reads 2.4 below the room, so it is asked for two
    # degrees less than the room is being driven to. The room is still judged on its own sensor.
    cold = Home(temp=25.0, outdoor=24.0, ac=True, options=options)
    _teach(cold, unit_offset=-2.4, _offset_count=50)
    cold.cycle()
    driven = cold.data_now["evaluations"]["target"].effective_target
    assert driven <= 22 and cold.states["climate.ac"].attributes["temperature"] == driven - 2

    # Quiet pre-cool (opt-in). Quiet starts at 13:00; the taught room would pass the 23 limit
    # overnight, so cooling starts ahead of it although the room is not above the setpoint.
    quiet = {**options, "quiet_hours": True, "quiet_start": "13:00", "quiet_end": "21:00", "quiet_max_temp": 23.0}
    early = Home(temp=21.8, outdoor=30.0, ac=True, options={**quiet, "quiet_precool": True})
    _teach(early)
    early.cycle()
    assert early.state("climate.ac") == "off"                              # 12:20, too early: the unit needs ~25 min
    clock.now = datetime(2026, 7, 15, 12, 45, tzinfo=timezone.utc)
    for opted_in, expected in ((True, "cool"), (False, "off")):
        room = Home(temp=21.8, outdoor=30.0, ac=True, options={**quiet, "quiet_precool": opted_in})
        _teach(room)
        room.cycle()
        assert room.state("climate.ac") == expected
    cool_night = Home(temp=21.8, outdoor=14.0, ac=True, options={**quiet, "quiet_precool": True})
    _teach(cool_night)
    cool_night.cycle()
    assert cool_night.state("climate.ac") == "off"                         # the night will be fine: nothing to bank

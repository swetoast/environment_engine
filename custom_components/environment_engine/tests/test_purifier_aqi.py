"""AQI-driven purifier: run/off, speed tiers, ionizer surge, and CO2/VOC fallback."""
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.const import ACTION_NONE, ACTION_OFF, ACTION_ON
from custom_components.environment_engine.evaluators import evaluate_air_quality
from custom_components.environment_engine.resolvers import resolve_purifier
from custom_components.environment_engine.snapshot import Snapshot


def _opts():
    return make_options(aqi_threshold=50, pm25_threshold=35, pm10_threshold=75)


def _caps(**kw):
    base = dict(climate=False, temperature=False, humidity=False, weather=False, occupancy=False,
                windows=False, pricing=False, air_quality=False, blinds=False, illuminance=False,
                fan=False, purifier=False, humidifier=False, ionizer=False, ventilation=False, smoke=False,
                lightning=False, outlet_overload=False)
    base.update(kw)
    return Capabilities(**base)


def _snap(**kw):
    d = dict(indoor_temp=22.0, humidity=50.0, outdoor_temp=18.0, occupancy=True, window_open=False,
             energy_price=None, co2=None, voc=None, hvac_mode="off", hvac_modes=["off"], sun_up=True,
             smoke_detected=False, outlet_overloaded=False)
    d.update(kw)
    return Snapshot(**d)


def _ev(snap):
    return {"air_quality": evaluate_air_quality(snap, _opts())}


def test_aqi_elevated_runs_purifier_low():
    # clearly elevated AQI (past the deadband above the 50 threshold)
    snap = _snap(aqi=65.0, aqi_dominant_factor="VOC")
    caps = _caps(purifier=True, air_quality=True)
    action, speed, ionizer, driver = resolve_purifier(caps, _opts(), _ev(snap))
    assert action == ACTION_ON
    assert speed == "low"


def test_aqi_good_turns_purifier_off():
    snap = _snap(aqi=30.0)
    action, speed, ionizer, _ = resolve_purifier(_caps(purifier=True, air_quality=True), _opts(), _ev(snap))
    assert action == ACTION_OFF


def test_aqi_speed_tiers_scale_up():
    caps = _caps(purifier=True, air_quality=True)
    assert resolve_purifier(caps, _opts(), _ev(_snap(aqi=90.0)))[1] == "medium"
    assert resolve_purifier(caps, _opts(), _ev(_snap(aqi=130.0)))[1] == "high"


def test_ionizer_surge_mode_waits_for_heavy_pollution():
    caps = _caps(purifier=True, air_quality=True, ionizer=True)
    surge = make_options(aqi_threshold=50, pm25_threshold=35, pm10_threshold=75, ionizer_mode="surge")
    # mild elevation -> ionizer stays off in 'surge' mode
    assert resolve_purifier(caps, surge, _ev(_snap(aqi=60.0)))[2] == ACTION_OFF
    # strong surge (pressure >= 0.6 -> AQI >= 110) -> ionizer on
    assert resolve_purifier(caps, surge, _ev(_snap(aqi=125.0)))[2] == ACTION_ON


def test_ionizer_runs_with_the_purifier_by_default():
    caps = _caps(purifier=True, air_quality=True, ionizer=True)
    # default mode: the ionizer runs whenever the purifier does -- no unreachable surge
    assert resolve_purifier(caps, _opts(), _ev(_snap(aqi=60.0)))[2] == ACTION_ON


def test_no_ionizer_capability_leaves_it_untouched():
    caps = _caps(purifier=True, air_quality=True)  # no ionizer
    assert resolve_purifier(caps, _opts(), _ev(_snap(aqi=125.0)))[2] == ACTION_NONE


def test_falls_back_to_co2_voc_without_aqi_sensor():
    # no AQI attribute -> raw component path; high VOC drives it
    snap = _snap(voc=700.0)
    res = evaluate_air_quality(snap, _opts())
    assert res.purifier_recommended is True
    assert res.dominant == "VOC"


def test_aqi_dominant_factor_surfaces_in_reason():
    snap = _snap(aqi=80.0, aqi_dominant_factor="CO2")
    assert "CO2" in evaluate_air_quality(snap, _opts()).reason


def test_outdoor_event_triggers_seal():
    res = evaluate_air_quality(_snap(aqi=40.0, outdoor_aqi=160.0), _opts())
    assert res.seal is True
    assert res.purifier_recommended is True
    assert res.pressure >= 0.8
    assert "sealing" in res.reason


def test_outdoor_below_threshold_no_seal():
    assert evaluate_air_quality(_snap(aqi=40.0, outdoor_aqi=40.0), _opts()).seal is False


def test_seal_forces_purifier_high_and_ionizer():
    caps = _caps(purifier=True, air_quality=True, ionizer=True)
    ev = {"air_quality": evaluate_air_quality(_snap(outdoor_aqi=200.0), _opts())}
    action, speed, ionizer, _ = resolve_purifier(caps, _opts(), ev)
    assert action == ACTION_ON and speed == "high" and ionizer == ACTION_ON


def test_sleep_caps_purifier_speed():
    caps = _caps(purifier=True, air_quality=True)
    ev = {"air_quality": evaluate_air_quality(_snap(aqi=130.0), _opts())}
    assert resolve_purifier(caps, _opts(), ev, sleep=True)[1] == "medium"
    assert resolve_purifier(caps, _opts(), ev, sleep=False)[1] == "high"


def test_seal_overrides_sleep_quiet():
    caps = _caps(purifier=True, air_quality=True)
    ev = {"air_quality": evaluate_air_quality(_snap(outdoor_aqi=200.0), _opts())}
    assert resolve_purifier(caps, _opts(), ev, sleep=True)[1] == "high"


def test_fine_pm_indoor_event_purifies_hard():
    res = evaluate_air_quality(_snap(pm25=70.0), _opts())  # 2x threshold, outdoor clean
    assert res.indoor_event is True and res.seal is False
    assert res.dominant == "PM2.5"
    assert res.pressure >= 0.9


def test_coarse_pm_gets_a_gentler_response():
    res = evaluate_air_quality(_snap(pm10=75.0), _opts())  # at threshold
    assert res.indoor_event is True and res.dominant == "PM10"
    caps = _caps(purifier=True, air_quality=True)
    assert resolve_purifier(caps, _opts(), {"air_quality": res})[1] == "medium"  # coarse weighted lower


def test_outdoor_event_beats_indoor_pm():
    res = evaluate_air_quality(_snap(pm25=100.0, outdoor_aqi=200.0), _opts())
    assert res.seal is True and res.indoor_event is False  # seal, don't air out


def test_low_pm_is_no_event():
    res = evaluate_air_quality(_snap(pm25=10.0, pm10=20.0), _opts())
    assert res.indoor_event is False and res.seal is False

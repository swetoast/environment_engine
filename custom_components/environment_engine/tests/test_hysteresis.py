"""Rate-limiting behavior: first-commit, suppression, per-channel independence,
and the purifier-speed downshift-slower asymmetry."""
from datetime import datetime, timedelta, timezone
from custom_components.environment_engine.decision import Decision
from custom_components.environment_engine.hysteresis import HysteresisEngine
from custom_components.environment_engine.const import ACTION_CLOSE, ACTION_NONE, ACTION_OFF, ACTION_ON, HVAC_COOL, HVAC_FAN_ONLY, HVAC_OFF


def _d(**kw):
    base = dict(strategy="s", hvac_mode=None, target_temperature=None, fan_action=ACTION_NONE, fan_speed=None,
                cover_action=ACTION_NONE, purifier_action=ACTION_NONE, confidence=1.0, reason="r")
    base.update(kw)
    return Decision(**base)


def test_first_decision_always_passes():
    eng = HysteresisEngine()
    out = eng.apply(_d(purifier_action=ACTION_ON), 3600)
    assert out.purifier_action == ACTION_ON


def test_zero_interval_allows_every_change():
    eng = HysteresisEngine()
    eng.apply(_d(purifier_action=ACTION_ON), 0)
    out = eng.apply(_d(purifier_action=ACTION_OFF), 0)
    assert out.purifier_action == ACTION_OFF


def test_change_within_interval_is_suppressed():
    eng = HysteresisEngine()
    eng.apply(_d(purifier_action=ACTION_ON), 3600)
    out = eng.apply(_d(purifier_action=ACTION_OFF), 3600)
    assert out.purifier_action == ACTION_NONE  # held: too soon to change


def test_blocked_decision_bypasses_rate_limit():
    eng = HysteresisEngine()
    eng.apply(_d(purifier_action=ACTION_ON), 3600)
    out = eng.apply(_d(strategy="safety", purifier_action=ACTION_OFF, blocked=True), 3600)
    assert out.purifier_action == ACTION_OFF and out.blocked


def test_channels_are_independent():
    eng = HysteresisEngine()
    eng.apply(_d(cover_action=ACTION_CLOSE, purifier_action=ACTION_ON), 3600)
    # cover unchanged (stays), purifier flip suppressed -> proves per-channel gating
    out = eng.apply(_d(cover_action=ACTION_CLOSE, purifier_action=ACTION_OFF), 3600)
    assert out.cover_action == ACTION_CLOSE
    assert out.purifier_action == ACTION_NONE


def test_purifier_speed_downshift_waits_twice_as_long():
    past = datetime.now(timezone.utc) - timedelta(seconds=100)
    # committed HIGH 100s ago; a downshift needs 2x60=120s -> still held
    down = HysteresisEngine()
    down._committed["purifier_speed"] = "high"
    down._changed_at["purifier_speed"] = past
    assert down.apply(_d(purifier_speed="medium"), 60).purifier_speed == "high"
    # committed LOW 100s ago; an upshift needs only 60s -> allowed at the same age
    up = HysteresisEngine()
    up._committed["purifier_speed"] = "low"
    up._changed_at["purifier_speed"] = past
    assert up.apply(_d(purifier_speed="high"), 60).purifier_speed == "high"


def test_compressor_holds_off_within_min_cycle():
    eng = HysteresisEngine()
    eng.apply(_d(hvac_mode=HVAC_COOL), 0)  # compressor starts
    out = eng.apply(_d(hvac_mode=HVAC_OFF), 0, compressor_min_cycle=3600)
    assert out.hvac_mode == HVAC_COOL  # min on-time protects the compressor


def test_compressor_holds_restart_within_min_cycle():
    eng = HysteresisEngine()
    eng.apply(_d(hvac_mode=HVAC_COOL), 0)
    eng.apply(_d(hvac_mode=HVAC_OFF), 0)  # allowed to stop (cycle 0)
    out = eng.apply(_d(hvac_mode=HVAC_COOL), 0, compressor_min_cycle=3600)
    assert out.hvac_mode == HVAC_OFF  # min off-time before restart


def test_compressor_guard_disabled_when_zero():
    eng = HysteresisEngine()
    eng.apply(_d(hvac_mode=HVAC_COOL), 0)
    out = eng.apply(_d(hvac_mode=HVAC_OFF), 0, compressor_min_cycle=0)
    assert out.hvac_mode == HVAC_OFF


def test_fan_only_is_not_a_compressor_transition():
    eng = HysteresisEngine()
    eng.apply(_d(hvac_mode=HVAC_FAN_ONLY), 0)  # no compressor
    out = eng.apply(_d(hvac_mode=HVAC_OFF), 0, compressor_min_cycle=3600)
    assert out.hvac_mode == HVAC_OFF

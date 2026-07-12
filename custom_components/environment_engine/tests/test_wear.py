"""Wear protection: minimum on/off cycle for motorized on/off devices."""
from custom_components.environment_engine.const import ACTION_NONE, ACTION_OFF, ACTION_ON
from custom_components.environment_engine.decision import Decision
from custom_components.environment_engine.hysteresis import HysteresisEngine


def _d(fan=ACTION_NONE, purifier=ACTION_NONE):
    return Decision("test", None, None, fan, "low", ACTION_NONE, purifier, 0.5, "r")


def test_fan_holds_on_through_min_cycle():
    h = HysteresisEngine()
    h.apply(_d(fan=ACTION_ON), minimum_interval=0, device_min_cycle=120)   # fan starts
    out = h.apply(_d(fan=ACTION_OFF), minimum_interval=0, device_min_cycle=120)  # tries to stop immediately
    assert out.fan_action != ACTION_OFF  # held on -- wear protection


def test_purifier_holds_through_min_cycle():
    h = HysteresisEngine()
    h.apply(_d(purifier=ACTION_ON), minimum_interval=0, device_min_cycle=120)
    out = h.apply(_d(purifier=ACTION_OFF), minimum_interval=0, device_min_cycle=120)
    assert out.purifier_action == ACTION_ON  # held on


def test_disabled_when_zero():
    h = HysteresisEngine()
    h.apply(_d(fan=ACTION_ON), minimum_interval=0, device_min_cycle=0)
    out = h.apply(_d(fan=ACTION_OFF), minimum_interval=0, device_min_cycle=0)
    assert out.fan_action == ACTION_OFF  # no wear guard -> stops freely

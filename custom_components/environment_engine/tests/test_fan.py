"""Fan resolver: independent triggers incl. comfort breeze and air-cleaning assist."""
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.const import ACTION_NONE, ACTION_OFF, ACTION_ON, STRATEGY_AIR_CIRCULATION, STRATEGY_AIR_QUALITY
from custom_components.environment_engine.resolvers import resolve_fan


def _opts(fan_comfort=True):
    return make_options(fan_comfort=fan_comfort)


def _caps(**kw):
    base = dict(climate=False, temperature=False, humidity=False, weather=False, occupancy=False, windows=False,
                pricing=False, air_quality=False, blinds=False, illuminance=False, fan=True, purifier=False,
                humidifier=False, ionizer=False, ventilation=False, smoke=False, lightning=False, outlet_overload=False)
    base.update(kw)
    return Capabilities(**base)


class _T:
    def __init__(self, c): self.confidence = c; self.reason = "t"


class _M:
    def __init__(self, a=False): self.airflow_recommended = a; self.risk = 0.0


class _AQ:
    def __init__(self, rec=False, p=0.0): self.purifier_recommended = rec; self.pressure = p; self.reason = "aq"; self.seal = False


def _ev(thermal=0.0, mold=False, aq_rec=False, aq_p=0.0):
    return {"thermal": _T(thermal), "mold": _M(mold), "air_quality": _AQ(aq_rec, aq_p)}


def test_cooling_demand_runs_and_boosts_fan():
    action, speed, _ = resolve_fan(None, _caps(), _opts(), _ev(thermal=0.5), False)
    assert action == ACTION_ON and speed in ("medium", "high")


def test_comfort_breeze_when_warm_but_not_cool_worthy():
    action, speed, driver = resolve_fan(None, _caps(), _opts(fan_comfort=True), _ev(thermal=0.2), False)
    assert action == ACTION_ON and speed == "low" and driver == STRATEGY_AIR_CIRCULATION


def test_comfort_breeze_can_be_disabled():
    action, _, _ = resolve_fan(None, _caps(), _opts(fan_comfort=False), _ev(thermal=0.2), False)
    assert action == ACTION_OFF


def test_fan_assists_air_cleaning_at_normal_aqi():
    # purifier recommended (AQI elevated) but below the old 0.35 fan bar -> fan still helps on low
    action, speed, driver = resolve_fan(None, _caps(air_quality=True), _opts(), _ev(aq_rec=True, aq_p=0.05), False)
    assert action == ACTION_ON and speed == "low" and driver == STRATEGY_AIR_QUALITY


def test_fan_goes_medium_for_strong_air_quality():
    _, speed, _ = resolve_fan(None, _caps(air_quality=True), _opts(), _ev(aq_rec=True, aq_p=0.5), False)
    assert speed == "medium"


def test_no_fan_capability_is_noop():
    action, _, _ = resolve_fan(None, _caps(fan=False), _opts(), _ev(thermal=0.5), False)
    assert action == ACTION_NONE


def test_sleep_caps_fan_to_low():
    _, speed, _ = resolve_fan(None, _caps(), _opts(), _ev(thermal=0.6), False, sleep=True)
    assert speed == "low"

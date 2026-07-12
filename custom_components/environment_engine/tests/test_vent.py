"""A portable AC's exhaust is vented only by its OWN vent contact or the manual switch.

Regression: a generic door/window contact used to satisfy `vented`, so opening a door
made the engine think the exhaust hose was vented and start cooling into a closed room.
"""
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.const import HVAC_COOL, HVAC_FAN_ONLY
from custom_components.environment_engine.resolvers import resolve_climate
from custom_components.environment_engine.snapshot import Snapshot


def _caps():
    return Capabilities(climate=True, temperature=True, humidity=False, weather=False, occupancy=False,
                        windows=True, pricing=False, air_quality=False, blinds=False, illuminance=False,
                        fan=False, purifier=False, humidifier=False, ionizer=False, ventilation=False,
                        smoke=False, lightning=False, outlet_overload=False)


def _snap(window_open, vented):
    return Snapshot(indoor_temp=27.0, humidity=50.0, outdoor_temp=20.0, occupancy=True,
                    window_open=window_open, energy_price=None, co2=None, voc=None, hvac_mode="off",
                    hvac_modes=["off", "cool", "dry", "fan_only"], min_temp=16.0, max_temp=30.0,
                    climate_valid=True, portable_ac=True, vented=vented)


class _T:
    def __init__(self, c): self.confidence = c


class _M:
    risk = 0.0
    airflow_recommended = False
    confidence = 0.0


class _H:
    confidence = 0.0


class _Tgt:
    effective_target = 22


def _ev():
    return {"thermal": _T(0.6), "mold": _M(), "humidity": _H(), "target": _Tgt()}


def test_open_door_alone_does_not_allow_portable_to_cool():
    # window/door open, but the exhaust vent is NOT -> must not cool
    mode, _, _ = resolve_climate(_snap(window_open=True, vented=False), _caps(), make_options(portable_ac=True), _ev(), False)
    assert mode != HVAC_COOL
    assert mode == HVAC_FAN_ONLY  # circulate only


def test_vent_contact_allows_portable_to_cool():
    mode, _, _ = resolve_climate(_snap(window_open=False, vented=True), _caps(), make_options(portable_ac=True), _ev(), False)
    assert mode == HVAC_COOL

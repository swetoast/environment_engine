"""Decode Home Assistant `supported_features` bitmasks into capability flags.

Reads the live bitmask each device reports so the engine knows what an actuator
can actually do -- set a target temperature, set a speed, position a cover --
rather than assuming the command is valid because the entity exists. Uses the
HA enums when importable (so it tracks renumbering) and falls back to the
documented literal bits otherwise.
"""
from __future__ import annotations
from dataclasses import dataclass
try:
    from homeassistant.components.climate import ClimateEntityFeature
except Exception:  # pragma: no cover - HA not importable in unit tests
    ClimateEntityFeature = None
try:
    from homeassistant.components.fan import FanEntityFeature
except Exception:  # pragma: no cover
    FanEntityFeature = None
try:
    from homeassistant.components.cover import CoverEntityFeature
except Exception:  # pragma: no cover
    CoverEntityFeature = None


def _bit(enum, name: str, fallback: int) -> int:
    if enum is not None and hasattr(enum, name):
        flag = getattr(enum, name)
        return int(getattr(flag, "value", flag))
    return fallback


def _supported(state) -> int | None:
    if state is None:
        return None
    try:
        return int(state.attributes.get("supported_features"))
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class ClimateFeatures:
    target_temperature: bool = True
    turn_off: bool = True
    fan_mode: bool = False


@dataclass(slots=True)
class FanFeatures:
    set_speed: bool = True
    preset_mode: bool = False


@dataclass(slots=True)
class CoverFeatures:
    open_close: bool = True
    set_position: bool = False


def climate_features(state) -> ClimateFeatures:
    features = _supported(state)
    if not features:  # missing or 0 -> assume capable, preserve prior behaviour
        return ClimateFeatures()
    return ClimateFeatures(
        target_temperature=bool(features & _bit(ClimateEntityFeature, "TARGET_TEMPERATURE", 1)),
        turn_off=bool(features & _bit(ClimateEntityFeature, "TURN_OFF", 128)),
        fan_mode=bool(features & _bit(ClimateEntityFeature, "FAN_MODE", 8)),
    )


def fan_features(state) -> FanFeatures:
    features = _supported(state)
    if features is None:
        # no bitmask reported -> infer speed support from percentage attributes
        attrs = {} if state is None else state.attributes
        return FanFeatures(set_speed="percentage" in attrs or "percentage_step" in attrs, preset_mode=bool(attrs.get("preset_modes")))
    return FanFeatures(
        set_speed=bool(features & _bit(FanEntityFeature, "SET_SPEED", 1)),
        preset_mode=bool(features & _bit(FanEntityFeature, "PRESET_MODE", 8)),
    )


def cover_features(state) -> CoverFeatures:
    features = _supported(state)
    if not features:
        return CoverFeatures()
    return CoverFeatures(
        open_close=bool(features & (_bit(CoverEntityFeature, "OPEN", 1) | _bit(CoverEntityFeature, "CLOSE", 2))),
        set_position=bool(features & _bit(CoverEntityFeature, "SET_POSITION", 4)),
    )

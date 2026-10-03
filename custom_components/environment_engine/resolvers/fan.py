from __future__ import annotations
from ..confidence import speed_tier
from ..const import (
    ACTION_NONE, ACTION_OFF, ACTION_ON,
    STRATEGY_AIR_CIRCULATION, STRATEGY_MOLD_PREVENTION, STRATEGY_PASSIVE_VENTILATION,
)


def resolve_fan(snapshot, capabilities, options, ev, passive_cooling, sleep=False):
    """Decide the fan actuator alone. Returns (action, speed|None, driver|None).

    A fan moves air. It answers heat (circulation, a comfort breeze, pulling cooler air
    through an open window) and damp (airflow against mould). It does NOT answer air
    quality: a fan filters nothing, so stirring a room that has particles in it only
    keeps them airborne. Air quality belongs to the purifier resolver alone, and nothing
    in here reads it. The two devices share a Home Assistant domain and nothing else.
    """
    if not capabilities.fan:
        return ACTION_NONE, None, None
    action, speed, driver = _decide_fan(options, ev["thermal"], ev["mold"], passive_cooling)
    if sleep and action == ACTION_ON:
        speed = "low"  # quiet at night
    return action, speed, driver


def _decide_fan(options, thermal, mold, passive_cooling):
    # Cooling demand: circulate, and boost an actively cooling AC.
    if thermal.confidence >= 0.3:
        return ACTION_ON, speed_tier(thermal.confidence, 0.8, 0.5), STRATEGY_AIR_CIRCULATION
    if mold.airflow_recommended:
        return ACTION_ON, "low", STRATEGY_MOLD_PREVENTION
    if passive_cooling and thermal.confidence >= 0.15:
        return ACTION_ON, "medium", STRATEGY_PASSIVE_VENTILATION
    # Gentle comfort breeze when it is warm but not yet cool-worthy (opt-out).
    if options.fan_comfort and thermal.confidence >= 0.15:
        return ACTION_ON, "low", STRATEGY_AIR_CIRCULATION
    return ACTION_OFF, None, None

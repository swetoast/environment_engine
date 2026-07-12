from __future__ import annotations
from ..confidence import speed_tier
from ..const import (
    ACTION_NONE, ACTION_OFF, ACTION_ON,
    STRATEGY_AIR_CIRCULATION, STRATEGY_AIR_QUALITY, STRATEGY_MOLD_PREVENTION, STRATEGY_PASSIVE_VENTILATION,
)


def resolve_fan(snapshot, capabilities, options, ev, passive_cooling, sleep=False):
    """Decide the fan actuator alone, independent of any climate. Returns
    (action, speed|None, driver|None). The fan can run alongside an active
    climate (circulation boost, via the shared thermal trigger) or entirely on
    its own -- for air quality, mold, passive ventilation, or a gentle comfort
    breeze before the AC is warranted."""
    if not capabilities.fan:
        return ACTION_NONE, None, None
    thermal = ev["thermal"]
    mold = ev["mold"]
    air_quality = ev["air_quality"]
    action, speed, driver = _decide_fan(snapshot, capabilities, options, thermal, mold, air_quality, passive_cooling)
    # Quiet at night: cap the fan to a whisper unless an outdoor event needs airflow.
    if sleep and action == ACTION_ON and not air_quality.seal:
        speed = "low"
    return action, speed, driver


def _decide_fan(snapshot, capabilities, options, thermal, mold, air_quality, passive_cooling):
    # Cooling demand -> circulate (and boost an actively cooling AC).
    if thermal.confidence >= 0.3:
        return ACTION_ON, speed_tier(thermal.confidence, 0.8, 0.5), STRATEGY_AIR_CIRCULATION
    # Assist air cleaning whenever air quality is elevated enough to run the
    # purifier (fan-follows-purifier), not just at the higher fan-only bar.
    if capabilities.air_quality and air_quality.purifier_recommended:
        return ACTION_ON, "medium" if air_quality.pressure >= 0.35 else "low", STRATEGY_AIR_QUALITY
    if mold.airflow_recommended:
        return ACTION_ON, "low", STRATEGY_MOLD_PREVENTION
    if passive_cooling and thermal.confidence >= 0.15:
        return ACTION_ON, "medium", STRATEGY_PASSIVE_VENTILATION
    # Gentle comfort breeze when it's warm but not yet cool-worthy (opt-out).
    if options.fan_comfort and thermal.confidence >= 0.15:
        return ACTION_ON, "low", STRATEGY_AIR_CIRCULATION
    return ACTION_OFF, None, None

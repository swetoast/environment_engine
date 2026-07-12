from __future__ import annotations
from ..confidence import speed_tier
from ..const import ACTION_NONE, ACTION_OFF, ACTION_ON, IONIZER_NEVER, IONIZER_WITH_PURIFIER, STRATEGY_AIR_QUALITY

_IONIZER_SURGE = 0.6  # 'surge' mode: air-quality pressure above this engages the ionizer


def resolve_purifier(capabilities, options, ev, sleep=False):
    """Decide purifier run state, speed, and ionizer together. Returns
    (action, speed|None, ionizer_action, driver|None).

    Run/off comes from the air-quality signal (AQI sensor when present, else
    CO2/VOC). Speed scales with the pressure magnitude. The ionizer follows the
    user's chosen mode: with the purifier (default), only on a strong pollution
    surge, or never. At night the speed is capped for quiet, unless an outdoor
    air-quality event demands full power.
    """
    if not capabilities.purifier or not capabilities.air_quality:
        return ACTION_NONE, None, ACTION_NONE, None
    aq = ev["air_quality"]
    ionizer_idle = ACTION_OFF if capabilities.ionizer else ACTION_NONE
    if aq.purifier_recommended:
        speed = speed_tier(aq.pressure, 0.66, 0.33)
        if sleep and not aq.seal and speed == "high":
            speed = "medium"  # keep it quieter overnight
        ionizer = ionizer_idle
        if capabilities.ionizer and options.ionizer_mode != IONIZER_NEVER:
            if options.ionizer_mode == IONIZER_WITH_PURIFIER or aq.pressure >= _IONIZER_SURGE:
                ionizer = ACTION_ON
        return ACTION_ON, speed, ionizer, STRATEGY_AIR_QUALITY
    if aq.pressure < 0.15:
        return ACTION_OFF, None, ionizer_idle, None
    return ACTION_NONE, None, ACTION_NONE, None

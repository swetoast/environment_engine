from __future__ import annotations
from ..const import ACTION_NONE, ACTION_OFF, ACTION_ON, STRATEGY_FRESH_AIR

_DEADBAND = 150  # ppm below the threshold before ventilation stops (anti-flap)


def resolve_ventilation(snapshot, capabilities, options, ev):
    """Bring in fresh air when CO2 is high -- a purifier filters particles but
    can't remove CO2, so stuffiness needs actual ventilation. Suppressed during
    an outdoor air-quality event (don't pull in smoke/pollen). Returns
    (action, driver|None)."""
    if not capabilities.ventilation:
        return ACTION_NONE, None
    aq = ev["air_quality"]
    if aq.seal:
        return ACTION_OFF, None  # sealed against bad outdoor air
    if aq.indoor_event:
        return ACTION_ON, STRATEGY_FRESH_AIR  # clear an indoor source with clean outdoor air
    co2 = snapshot.co2
    if co2 is None:
        return ACTION_NONE, None
    if co2 >= options.co2_ventilate:
        return ACTION_ON, STRATEGY_FRESH_AIR
    if co2 < options.co2_ventilate - _DEADBAND:
        return ACTION_OFF, None
    return ACTION_NONE, None

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
    # Air out pre-emptively: if the room is getting stuffy and the outdoor AQI forecast
    # says the air is about to turn bad, take the chance to ventilate now, while it is
    # still clean. Once outdoor AQI crosses the seal threshold the window closes -- the
    # engine would then have to keep the room shut and the CO2 would keep climbing.
    soon_bad = (snapshot.outdoor_aqi_soon is not None
                and snapshot.outdoor_aqi_soon >= options.outdoor_aqi_threshold)
    outdoor_ok_now = (snapshot.outdoor_aqi is None
                      or snapshot.outdoor_aqi < options.outdoor_aqi_threshold)
    if soon_bad and outdoor_ok_now and co2 >= options.co2_ventilate - _DEADBAND:
        return ACTION_ON, STRATEGY_FRESH_AIR   # ventilate now, before the window shuts
    if co2 < options.co2_ventilate - _DEADBAND:
        return ACTION_OFF, None
    return ACTION_NONE, None

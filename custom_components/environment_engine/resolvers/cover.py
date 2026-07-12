from __future__ import annotations
from ..const import ACTION_CLOSE, ACTION_NONE, ACTION_OPEN, STRATEGY_SOLAR_MITIGATION
def resolve_cover(snapshot, capabilities, ev):
    """Decide the cover/blinds actuator alone. Returns (action, driver|None).

    Closes against solar load -- measured light (lux glare) and/or heat. Reopen
    is the subtle part: an indoor lux sensor reads lower once the blinds shut, so
    using lux to decide reopen creates an oscillation (close -> lux drops ->
    "dim, reopen" -> lux rises -> close). To avoid that:
      * with a lux sensor, reopen only after sundown (a blind-independent event);
      * without one, the heat signal is blind-independent, so daylight reopen
        once the load clears is safe.
    """
    if not capabilities.blinds:
        return ACTION_NONE, None
    solar = ev["solar"]
    if solar.shading_recommended:
        return ACTION_CLOSE, STRATEGY_SOLAR_MITIGATION
    if snapshot.cover_closed:
        if capabilities.illuminance:
            if not snapshot.sun_up:
                return ACTION_OPEN, STRATEGY_SOLAR_MITIGATION
        elif snapshot.sun_up and solar.pressure < 0.2:
            return ACTION_OPEN, STRATEGY_SOLAR_MITIGATION
    return ACTION_NONE, None

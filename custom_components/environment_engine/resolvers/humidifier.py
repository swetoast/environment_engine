from __future__ import annotations
from ..const import ACTION_NONE, ACTION_OFF, ACTION_ON, STRATEGY_DEHUMIDIFY, STRATEGY_HUMIDIFY
from ..evaluators import drying_pressure
def resolve_humidifier(snapshot, capabilities, options, ev):
    """Decide a humidifier-domain actuator alone. Returns (action, target|None, driver|None).

    The device_class sets direction: a `humidifier` adds moisture (runs when the
    room is too dry), a `dehumidifier` removes it (runs on the humidity/mold
    pressures). Dehumidifier is the default when the class is unknown, since
    that's what the engine's humidity/mold logic is built to relieve.
    """
    if not capabilities.humidifier:
        return ACTION_NONE, None, None
    target = options.target_humidity
    humidity = snapshot.humidity
    if snapshot.humidifier_class == "humidifier":
        if humidity is not None and humidity < target - 10:
            return ACTION_ON, target, STRATEGY_HUMIDIFY
        if humidity is None or humidity >= target:
            return ACTION_OFF, None, None
        return ACTION_NONE, None, None
    # dehumidifier (default direction)
    drying = drying_pressure(ev)
    if drying >= 0.3:
        return ACTION_ON, target, STRATEGY_DEHUMIDIFY
    if humidity is not None and humidity <= target - 5:
        return ACTION_OFF, None, None
    return ACTION_NONE, None, None

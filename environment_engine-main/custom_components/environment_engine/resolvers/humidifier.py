from __future__ import annotations
from ..const import ACTION_NONE, ACTION_OFF, ACTION_ON, STRATEGY_DEHUMIDIFY, STRATEGY_HUMIDIFY
from ..evaluators import drying_pressure
def resolve_humidifier(snapshot, capabilities, options, ev):
    """Decide a humidifier-domain actuator alone. Returns (action, target|None, driver|None).

    The device_class sets direction: a `humidifier` adds moisture (runs when the room is
    too dry), a `dehumidifier` removes it (runs on the humidity/mold pressures).

    A device that does not report its class is driven ONLY as an explicit `dehumidifier`.
    The engine will not *add* moisture to a room on a guess: if a humidifier failed to
    report its class, defaulting it to "dehumidifier" would run it exactly backwards --
    switching it ON when the room is already humid, wetting it further. So an unknown class
    gets the dehumidifier's stop-logic (safe: it can turn a device off) but never the
    start-logic, and it never humidifies. Set the device's class, or a `dehumidifier`
    device_class, to get active control.
    """
    if not capabilities.humidifier:
        return ACTION_NONE, None, None
    target = options.target_humidity
    humidity = snapshot.humidity
    device_class = snapshot.humidifier_class

    if device_class == "humidifier":
        if humidity is not None and humidity < target - 10:
            return ACTION_ON, target, STRATEGY_HUMIDIFY
        if humidity is None or humidity >= target:
            return ACTION_OFF, None, None
        return ACTION_NONE, None, None

    # Dehumidifier -- but only START one that actually declares itself a dehumidifier.
    known_dehumidifier = device_class == "dehumidifier"
    drying = drying_pressure(ev)
    if known_dehumidifier and drying >= 0.3:
        return ACTION_ON, target, STRATEGY_DEHUMIDIFY
    # Stopping is always safe, whatever the class: a dry-enough room needs neither.
    if humidity is not None and humidity <= target - 5:
        return ACTION_OFF, None, None
    return ACTION_NONE, None, None

from __future__ import annotations
from ..evaluators import drying_pressure
from ..const import (
    HVAC_COOL, HVAC_DRY, HVAC_FAN_ONLY, HVAC_OFF,
    STRATEGY_AIR_CIRCULATION, STRATEGY_COOLING, STRATEGY_DEHUMIDIFY,
    STRATEGY_MOLD_PREVENTION, STRATEGY_PASSIVE_VENTILATION, STRATEGY_QUIET_COOLING,
)
# Modes the engine actively manages. It stands these down when there is no
# demand, but never touches modes it does not manage (e.g. heat), so it won't
# fight a heating setup in winter.
_MANAGED = {HVAC_COOL, HVAC_DRY, HVAC_FAN_ONLY}


def resolve_climate(snapshot, capabilities, options, ev, passive_cooling):
    """Decide the climate actuator alone. Returns (hvac_mode|None, target|None, driver|None).

    hvac_mode is None when the engine should not touch the climate at all (no
    climate, climate offline, or a mode it does not manage).

    Two things can hold the compressor back:
      * a portable AC whose exhaust isn't vented (it would dump condenser heat indoors);
      * quiet hours, where the noise of the compressor isn't wanted -- unless the room has
        passed the "too hot" line, in which case comfort wins and it cools anyway.
    When the compressor is held back the unit falls back to its own fan_only to keep air
    moving. Outside quiet hours the AC only fans when there's no standalone fan to do it,
    so the two don't double up.
    """
    if not capabilities.climate or not snapshot.climate_valid:
        return None, None, None
    if not snapshot.temperature_valid:
        # The temperature sensor is missing or offline, so the room reading is a
        # placeholder, not a measurement. Don't act on it: standing the unit down here
        # would turn the AC off on a momentary sensor blip (and then anti-short-cycling
        # would delay the restart). Leave the unit alone -- it has its own thermostat and
        # keeps regulating to the setpoint we last gave it.
        return None, None, None
    modes = snapshot.hvac_modes
    thermal = ev["thermal"]
    mold = ev["mold"]
    drying = drying_pressure(ev)

    temp = snapshot.feels_like if snapshot.feels_like is not None else snapshot.indoor_temp
    too_hot_to_stay_quiet = temp is not None and temp >= options.quiet_max_temp
    quiet = snapshot.quiet and not too_hot_to_stay_quiet  # hold the compressor back
    vented_ok = not options.portable_ac or snapshot.vented
    can_cool = vented_ok and not quiet
    # During quiet hours the AC's own fan is the point, so it may fan even alongside a
    # standalone fan; otherwise it defers to the standalone fan to avoid double-fanning.
    ac_fan_ok = HVAC_FAN_ONLY in modes and (quiet or not capabilities.fan)

    if can_cool and capabilities.humidity and not capabilities.humidifier and drying > thermal.confidence and drying >= 0.3 and HVAC_DRY in modes:
        return HVAC_DRY, None, STRATEGY_DEHUMIDIFY
    if thermal.confidence >= 0.3:
        if passive_cooling and HVAC_FAN_ONLY in modes:
            return HVAC_FAN_ONLY, None, STRATEGY_PASSIVE_VENTILATION
        if can_cool and HVAC_COOL in modes:
            target = ev["target"].effective_target if "target" in ev else options.target
            return HVAC_COOL, target, STRATEGY_COOLING
        # Cooling is held back (quiet hours, or portable + unvented): keep air moving.
        if ac_fan_ok:
            return HVAC_FAN_ONLY, None, (STRATEGY_QUIET_COOLING if quiet else STRATEGY_AIR_CIRCULATION)
    # Gentle circulation via the AC when it's the only air mover in the room.
    if ac_fan_ok and options.fan_comfort and thermal.confidence >= 0.15:
        return HVAC_FAN_ONLY, None, (STRATEGY_QUIET_COOLING if quiet else STRATEGY_AIR_CIRCULATION)
    if mold.airflow_recommended and ac_fan_ok:
        return HVAC_FAN_ONLY, None, STRATEGY_MOLD_PREVENTION
    if snapshot.hvac_mode in _MANAGED:
        return HVAC_OFF, None, None
    return None, None, None

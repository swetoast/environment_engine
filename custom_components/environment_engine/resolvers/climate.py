from __future__ import annotations
from ..comfort import dehumidify_satisfied, should_dehumidify
from ..const import (
    HVAC_COOL, HVAC_DRY, HVAC_FAN_ONLY, HVAC_OFF,
    STRATEGY_AIR_CIRCULATION, STRATEGY_COOLING, STRATEGY_DEHUMIDIFY,
    STRATEGY_MOLD_PREVENTION, STRATEGY_PASSIVE_VENTILATION, STRATEGY_QUIET_COOLING,
)

# Modes the engine actively manages. It stands these down when there is no demand, but
# never touches modes it does not manage (e.g. heat), so it won't fight a heating setup.
_MANAGED = {HVAC_COOL, HVAC_DRY, HVAC_FAN_ONLY}


def resolve_climate(snapshot, capabilities, options, ev, passive_cooling):
    """Decide the climate actuator. Returns (hvac_mode|None, target|None, driver|None).

    The rule this file exists to enforce: **above the setpoint means cool.** Not humidity,
    not price, not a comfort model, not a fan that could theoretically make the room feel
    adequate -- none of them get to override that. The only thing that outranks it is safety.

    Everything else is context, and context may only make the engine cool *harder*, by
    lowering the setpoint upstream in target_resolver. It never gets to decide the room is
    fine when the thermometer says otherwise.

        1. safety blocked                    -> OFF            (handled by the planner)
        2. temperature reading invalid       -> hold, touch nothing
        3. above setpoint, cooling available -> COOL
           above setpoint, cooling blocked   -> FAN_ONLY, keep air moving while blocked
        4. at setpoint but air too wet       -> DRY
        5. circulation wanted                -> FAN_ONLY
        6. otherwise                         -> OFF
    """
    if not capabilities.climate or not snapshot.climate_valid:
        return None, None, None
    if not snapshot.temperature_valid:
        # The reading is a placeholder, not a measurement. Acting on it would turn a
        # happily-cooling unit off on a momentary sensor blip, and anti-short-cycling
        # would then delay the restart. The AC has its own thermostat; leave it be.
        return None, None, None

    modes = snapshot.hvac_modes
    mold = ev["mold"]
    # Two different numbers, deliberately:
    #   base   -- the temperature YOU asked for. Decides whether the room is too warm.
    #   target -- that, minus context (heat, sun, damp air, cheap power). Decides how
    #             hard to drive the unit once it is running.
    # Testing "too warm" against the driven-down number would be circular: the damp
    # penalty would lower the setpoint, that would make the room "above target", and DRY
    # could never fire because cooling always won.
    base = ev["target"].base_target if "target" in ev else int(options.target)
    target = ev["target"].effective_target if "target" in ev else int(options.target)
    indoor = snapshot.indoor_temp
    above_target = indoor is not None and indoor > base

    # What can stop the compressor -- note that "the room is comfortable" is not on the list.
    vented_ok = not options.portable_ac or snapshot.vented
    temp = snapshot.feels_like if snapshot.feels_like is not None else indoor
    too_hot_to_stay_quiet = temp is not None and temp >= options.quiet_max_temp
    quiet = snapshot.quiet and not too_hot_to_stay_quiet
    can_cool = vented_ok and not quiet

    # When the compressor is blocked and the room is still hot, the AC's own fan_only is
    # standing in for cooling it cannot do -- so it runs even alongside a standalone fan,
    # because every air mover helps and fan_only costs nothing but a little noise. It makes
    # no difference *why* the compressor is blocked: quiet hours and an unvented portable
    # are the same situation, and treating them differently was an arbitrary split.
    # (fan_only on an unvented portable is harmless: no compressor, so no condenser heat.)
    #
    # Outside that, the AC only fans when it is the room's only air mover -- two fans in one
    # room is just noise. A standalone fan that is configured but offline is not an air
    # mover, so the AC takes over rather than both sitting idle and leaving the room still.
    standalone_fan = capabilities.fan and snapshot.fan_available
    compressor_blocked = not can_cool
    ac_fan_ok = HVAC_FAN_ONLY in modes and (compressor_blocked or not standalone_fan)

    # --- 3. Above the setpoint: cool, or keep air moving if the compressor is blocked ---
    if above_target:
        # Free cooling first: if the outside air is doing the work through an open
        # window, spending compressor energy on top of it is just waste.
        if passive_cooling and HVAC_FAN_ONLY in modes:
            return HVAC_FAN_ONLY, None, STRATEGY_PASSIVE_VENTILATION
        if can_cool and HVAC_COOL in modes:
            return HVAC_COOL, target, STRATEGY_COOLING
        if ac_fan_ok:
            return HVAC_FAN_ONLY, None, (STRATEGY_QUIET_COOLING if quiet
                                               else STRATEGY_AIR_CIRCULATION)
        if standalone_fan:
            # A standalone fan is the better air mover and the fan resolver drives it;
            # two fans in one room is just noise.
            return (HVAC_OFF if snapshot.hvac_mode in _MANAGED else None), None, None

    # --- 4. At or below the setpoint, but the air is too wet ---
    elif capabilities.humidity and not capabilities.humidifier and HVAC_DRY in modes:
        already_drying = snapshot.hvac_mode == HVAC_DRY
        if already_drying and not dehumidify_satisfied(snapshot, options):
            return HVAC_DRY, None, STRATEGY_DEHUMIDIFY
        if not already_drying and should_dehumidify(snapshot, options, True):
            return HVAC_DRY, None, STRATEGY_DEHUMIDIFY

    # --- 5. Circulation ---
    # Passive ventilation is a *cooling* strategy, so it lives inside the above-target
    # branch above. A room that is already cool does not need the window's help.
    if ac_fan_ok and options.fan_comfort and above_target:
        return HVAC_FAN_ONLY, None, STRATEGY_AIR_CIRCULATION
    if mold.airflow_recommended and ac_fan_ok:
        return HVAC_FAN_ONLY, None, STRATEGY_MOLD_PREVENTION

    # --- 6. Nothing to do ---
    if snapshot.hvac_mode in _MANAGED:
        return HVAC_OFF, None, None
    return None, None, None

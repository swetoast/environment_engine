from __future__ import annotations
import logging
from homeassistant.const import ATTR_ENTITY_ID
from ..const import CONF_CLIMATE, HVAC_COOL, HVAC_DRY, HVAC_FAN_ONLY, HVAC_OFF
from ..entities import as_list
from ..features import climate_features
from ..units import from_celsius
from .common import controllable, is_assumed
_LOGGER = logging.getLogger(__name__)
# Modes the engine manages; it only stands these down, never a mode it does not drive.
_MANAGED = {HVAC_COOL, HVAC_DRY, HVAC_FAN_ONLY}
async def apply_climate(hass, config: dict, snapshot, decision) -> bool:
    if decision.hvac_mode is None:
        return True
    ok = True
    for entity_id in as_list(config.get(CONF_CLIMATE)):
        ok = await _apply_one(hass, entity_id, snapshot, decision) and ok
    return ok
async def _apply_one(hass, entity_id, snapshot, decision) -> bool:
    state = controllable(hass, entity_id)
    if state is None:
        return True
    assumed = is_assumed(state)
    modes = state.attributes.get("hvac_modes", []) or []
    feats = climate_features(state)

    # Hard safety backstop, independent of the resolver. The compressor modes dump
    # condenser heat down the exhaust hose; if that hose is not confirmed vented, running
    # them heats the room instead of cooling it. The resolver already gates this, but a
    # safety failure this direct deserves defence in depth: never *send* cool or dry to a
    # unit the snapshot says is unvented. Stand it down instead.
    if (decision.hvac_mode in (HVAC_COOL, HVAC_DRY)
            and getattr(snapshot, "vent_required", False)
            and not snapshot.vented):
        if state.state in _MANAGED and HVAC_OFF in modes:
            await hass.services.async_call("climate", "set_hvac_mode",
                {ATTR_ENTITY_ID: entity_id, "hvac_mode": HVAC_OFF}, blocking=True)
        return True
    try:
        if decision.hvac_mode == HVAC_OFF:
            if state.state == HVAC_OFF and not assumed:
                return True
            if HVAC_OFF in modes:
                await hass.services.async_call("climate", "set_hvac_mode", {ATTR_ENTITY_ID: entity_id, "hvac_mode": HVAC_OFF}, blocking=True)
            elif feats.turn_off:
                await hass.services.async_call("climate", "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True)
            return True
        if decision.hvac_mode not in modes:
            # The unit cannot do what was asked -- fan_only on a model without it, say.
            # Returning here would leave it in whatever it was doing, which may well be
            # cooling, so the engine would have decided "stop cooling" and the AC would
            # carry on. Stand it down instead; that is the safe reading of "not this".
            if state.state in _MANAGED and HVAC_OFF in modes:
                await hass.services.async_call("climate", "set_hvac_mode", {ATTR_ENTITY_ID: entity_id, "hvac_mode": HVAC_OFF}, blocking=True)
            return True
        if assumed or state.state != decision.hvac_mode:
            await hass.services.async_call("climate", "set_hvac_mode", {ATTR_ENTITY_ID: entity_id, "hvac_mode": decision.hvac_mode}, blocking=True)
        if decision.hvac_mode == HVAC_COOL and decision.target_temperature is not None and feats.target_temperature:
            # Floor in the unit's own scale. We choose a whole degree in Celsius, but a
            # Fahrenheit unit converts 22 C to 71.6 F -- a fraction the AC cannot accept,
            # so the whole-degree guarantee would be lost at the very last step. Floor
            # again here, and downward, so the conversion can only ever land colder.
            import math
            converted = float(from_celsius(float(decision.target_temperature), snapshot.temperature_unit))
            # Snap to the step the unit actually accepts, rounding DOWN so the conversion
            # can only ever land colder. Most air conditioners report a step of 1, which is
            # why the engine works in whole degrees -- but a unit that accepts 0.5 should
            # get the finer value rather than having it thrown away.
            try:
                step = float(state.attributes.get("target_temp_step") or 1.0)
            except (TypeError, ValueError):
                step = 1.0
            if step <= 0:
                step = 1.0
            target = math.floor(converted / step + 1e-9) * step
            target = round(target, 2)
            dmin, dmax = state.attributes.get("min_temp"), state.attributes.get("max_temp")
            if dmin is not None:
                target = max(target, float(dmin))
            if dmax is not None:
                target = min(target, float(dmax))
            current = state.attributes.get("temperature")
            try:
                if not assumed and current is not None and abs(float(current) - target) < 0.5:
                    return True
            except (TypeError, ValueError):
                pass
            await hass.services.async_call("climate", "set_temperature", {ATTR_ENTITY_ID: entity_id, "temperature": target}, blocking=True)
        return True
    except Exception:
        _LOGGER.exception("Failed to apply climate decision to %s", entity_id)
        return False

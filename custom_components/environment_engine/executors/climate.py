from __future__ import annotations
import logging
from homeassistant.const import ATTR_ENTITY_ID
from ..const import CONF_CLIMATE, HVAC_COOL, HVAC_FAN_ONLY, HVAC_OFF
from ..presets import preset_for_speed
from ..entities import as_list
from ..features import climate_features
from ..units import from_celsius
from .common import controllable, is_assumed
_LOGGER = logging.getLogger(__name__)
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
    try:
        if decision.hvac_mode == HVAC_OFF:
            if state.state == HVAC_OFF and not assumed:
                return True
            if HVAC_OFF in modes:
                await hass.services.async_call("climate", "set_hvac_mode", {ATTR_ENTITY_ID: entity_id, "hvac_mode": HVAC_OFF}, blocking=True)
            elif feats.turn_off:
                await hass.services.async_call("climate", "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True)
            return True
        if decision.hvac_mode not in modes:  # this unit doesn't support the mode
            return True
        if assumed or state.state != decision.hvac_mode:
            await hass.services.async_call("climate", "set_hvac_mode", {ATTR_ENTITY_ID: entity_id, "hvac_mode": decision.hvac_mode}, blocking=True)
        # When we run the unit for airflow (fan_only, or a cooling boost), actually set the
        # fan speed. Otherwise the AC stays on whatever it had -- usually 'auto'/'quiet' --
        # and "circulate to shed heat" barely moves any air. Map our tier onto the unit's
        # own fan modes; skip if it has none or is already there.
        if decision.hvac_mode in (HVAC_FAN_ONLY, HVAC_COOL) and decision.climate_fan_speed and feats.fan_mode:
            desired = preset_for_speed(state.attributes.get("fan_modes"), decision.climate_fan_speed)
            if desired is not None and (assumed or state.attributes.get("fan_mode") != desired):
                await hass.services.async_call("climate", "set_fan_mode", {ATTR_ENTITY_ID: entity_id, "fan_mode": desired}, blocking=True)
        if decision.hvac_mode == HVAC_COOL and decision.target_temperature is not None and feats.target_temperature:
            target = round(float(from_celsius(float(decision.target_temperature), snapshot.temperature_unit)), 1)
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

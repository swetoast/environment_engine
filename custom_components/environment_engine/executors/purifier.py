from __future__ import annotations
import logging
from homeassistant.const import ATTR_ENTITY_ID
from ..const import ACTION_OFF, ACTION_ON, CONF_PURIFIER
from ..entities import as_list
from ..features import fan_features
from ..presets import preset_for_speed
from .common import SPEED_TO_PERCENTAGE, controllable, is_assumed
_LOGGER = logging.getLogger(__name__)
async def apply_purifier(hass, config: dict, decision) -> bool:
    if decision.purifier_action not in (ACTION_ON, ACTION_OFF):
        return True
    ok = True
    for entity_id in as_list(config.get(CONF_PURIFIER)):
        ok = await _apply_one(hass, entity_id, decision) and ok
    return ok
async def _apply_one(hass, entity_id, decision) -> bool:
    state = controllable(hass, entity_id)
    if state is None:
        return True
    domain = entity_id.split(".", 1)[0]
    assumed = is_assumed(state)
    features = fan_features(state) if domain == "fan" else None
    # A purifier is driven by its OWN preset modes (Auto/Silent/Favorite/Turbo...) when it
    # has them -- it is not a fan. Percentage is only the fallback for devices with no presets.
    desired_preset = None
    if features is not None and features.preset_mode and decision.purifier_speed:
        desired_preset = preset_for_speed(state.attributes.get("preset_modes"), decision.purifier_speed)
    desired_pct = None
    if desired_preset is None and features is not None and features.set_speed and decision.purifier_speed:
        desired_pct = SPEED_TO_PERCENTAGE.get(decision.purifier_speed, 33)
    try:
        if decision.purifier_action == ACTION_OFF:
            if state.state == "off" and not assumed:
                return True
            await hass.services.async_call(domain, "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True)
            return True
        if state.state == "on" and not assumed:
            if desired_preset is not None:
                if state.attributes.get("preset_mode") == desired_preset:
                    return True
                await hass.services.async_call("fan", "set_preset_mode", {ATTR_ENTITY_ID: entity_id, "preset_mode": desired_preset}, blocking=True)
                return True
            if desired_pct is None:
                return True
            current = state.attributes.get("percentage")
            try:
                if current is not None and abs(float(current) - desired_pct) < 1:
                    return True
            except (TypeError, ValueError):
                pass
            await hass.services.async_call("fan", "set_percentage", {ATTR_ENTITY_ID: entity_id, "percentage": desired_pct}, blocking=True)
            return True
        data = {ATTR_ENTITY_ID: entity_id}
        if desired_preset is not None:
            data["preset_mode"] = desired_preset
        elif desired_pct is not None:
            data["percentage"] = desired_pct
        await hass.services.async_call(domain, "turn_on", data, blocking=True)
        return True
    except Exception:
        _LOGGER.exception("Failed to apply purifier decision to %s", entity_id)
        return False

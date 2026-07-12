from __future__ import annotations
import logging
from homeassistant.const import ATTR_ENTITY_ID
from ..const import ACTION_OFF, ACTION_ON, CONF_FAN
from ..entities import as_list
from ..features import fan_features
from .common import SPEED_TO_PERCENTAGE, controllable, is_assumed
_LOGGER = logging.getLogger(__name__)
async def apply_fan(hass, config: dict, snapshot, decision) -> bool:
    if decision.fan_action not in (ACTION_ON, ACTION_OFF):
        return True
    ok = True
    for entity_id in as_list(config.get(CONF_FAN)):
        ok = await _apply_one(hass, entity_id, decision) and ok
    return ok
async def _apply_one(hass, entity_id, decision) -> bool:
    state = controllable(hass, entity_id)
    if state is None:
        return True
    assumed = is_assumed(state)
    desired_pct = SPEED_TO_PERCENTAGE.get(decision.fan_speed, 33) if (decision.fan_speed and fan_features(state).set_speed) else None
    try:
        if decision.fan_action == ACTION_OFF:
            if state.state == "off" and not assumed:
                return True
            await hass.services.async_call("fan", "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True)
            return True
        if state.state == "on" and not assumed:
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
        if desired_pct is not None:
            data["percentage"] = desired_pct
        await hass.services.async_call("fan", "turn_on", data, blocking=True)
        return True
    except Exception:
        _LOGGER.exception("Failed to apply fan decision to %s", entity_id)
        return False

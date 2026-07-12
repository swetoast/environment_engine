from __future__ import annotations
import logging
from homeassistant.const import ATTR_ENTITY_ID
from ..const import ACTION_OFF, ACTION_ON, CONF_HUMIDIFIER
from ..entities import as_list
from .common import controllable, is_assumed
_LOGGER = logging.getLogger(__name__)
async def apply_humidifier(hass, config: dict, snapshot, decision) -> bool:
    if decision.humidifier_action not in (ACTION_ON, ACTION_OFF):
        return True
    ok = True
    for entity_id in as_list(config.get(CONF_HUMIDIFIER)):
        ok = await _apply_one(hass, entity_id, decision) and ok
    return ok
async def _apply_one(hass, entity_id, decision) -> bool:
    state = controllable(hass, entity_id)
    if state is None:
        return True
    assumed = is_assumed(state)
    try:
        if decision.humidifier_action == ACTION_OFF:
            if state.state == "off" and not assumed:
                return True
            await hass.services.async_call("humidifier", "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True)
            return True
        if state.state != "on" or assumed:
            await hass.services.async_call("humidifier", "turn_on", {ATTR_ENTITY_ID: entity_id}, blocking=True)
        if decision.humidifier_target is not None:
            lo = state.attributes.get("min_humidity", 0)
            hi = state.attributes.get("max_humidity", 100)
            target = int(max(min(float(decision.humidifier_target), float(hi)), float(lo)))
            current = state.attributes.get("humidity")
            try:
                if not assumed and current is not None and int(float(current)) == target:
                    return True
            except (TypeError, ValueError):
                pass
            await hass.services.async_call("humidifier", "set_humidity", {ATTR_ENTITY_ID: entity_id, "humidity": target}, blocking=True)
        return True
    except Exception:
        _LOGGER.exception("Failed to apply humidifier decision to %s", entity_id)
        return False

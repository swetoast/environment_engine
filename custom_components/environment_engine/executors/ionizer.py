from __future__ import annotations
import logging
from homeassistant.const import ATTR_ENTITY_ID
from ..const import ACTION_OFF, ACTION_ON, CONF_IONIZER
from ..entities import as_list
from .common import controllable, is_assumed
_LOGGER = logging.getLogger(__name__)
async def apply_ionizer(hass, config: dict, decision) -> bool:
    if decision.ionizer_action not in (ACTION_ON, ACTION_OFF):
        return True
    ok = True
    for entity_id in as_list(config.get(CONF_IONIZER)):
        ok = await _apply_one(hass, entity_id, decision) and ok
    return ok
async def _apply_one(hass, entity_id, decision) -> bool:
    state = controllable(hass, entity_id)
    if state is None:
        return True
    desired = "on" if decision.ionizer_action == ACTION_ON else "off"
    if state.state == desired and not is_assumed(state):
        return True
    try:
        domain = entity_id.split(".", 1)[0]
        await hass.services.async_call(domain, "turn_on" if decision.ionizer_action == ACTION_ON else "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True)
        return True
    except Exception:
        _LOGGER.exception("Failed to apply ionizer decision to %s", entity_id)
        return False

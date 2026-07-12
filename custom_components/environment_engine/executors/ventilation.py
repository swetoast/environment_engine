from __future__ import annotations
import logging
from homeassistant.const import ATTR_ENTITY_ID
from ..const import ACTION_OFF, ACTION_ON, CONF_VENTILATION
from ..entities import as_list
from .common import controllable, is_assumed
_LOGGER = logging.getLogger(__name__)
# A fresh-air device can be a fan/switch (on/off) or a vent cover (open/close).
_ON = {"fan": ("fan", "turn_on"), "switch": ("switch", "turn_on"), "cover": ("cover", "open_cover")}
_OFF = {"fan": ("fan", "turn_off"), "switch": ("switch", "turn_off"), "cover": ("cover", "close_cover")}
_OPEN_STATES = ("on", "open")
async def apply_ventilation(hass, config: dict, decision) -> bool:
    if decision.ventilation_action not in (ACTION_ON, ACTION_OFF):
        return True
    ok = True
    for entity_id in as_list(config.get(CONF_VENTILATION)):
        ok = await _apply_one(hass, entity_id, decision) and ok
    return ok
async def _apply_one(hass, entity_id, decision) -> bool:
    state = controllable(hass, entity_id, ("unavailable", "unknown", "opening", "closing"))
    if state is None:
        return True
    domain = entity_id.split(".", 1)[0]
    table = _ON if decision.ventilation_action == ACTION_ON else _OFF
    call = table.get(domain)
    if call is None:
        return True
    opening = decision.ventilation_action == ACTION_ON
    if not is_assumed(state):
        if opening and state.state in _OPEN_STATES:
            return True
        if not opening and state.state not in _OPEN_STATES:
            return True
    try:
        await hass.services.async_call(call[0], call[1], {ATTR_ENTITY_ID: entity_id}, blocking=True)
        return True
    except Exception:
        _LOGGER.exception("Failed to apply ventilation decision to %s", entity_id)
        return False

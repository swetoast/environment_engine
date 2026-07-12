from __future__ import annotations
import logging
from homeassistant.const import ATTR_ENTITY_ID
from ..const import ACTION_CLOSE, ACTION_OPEN, CONF_BLINDS
from ..entities import as_list
from ..features import cover_features
from .common import controllable, is_assumed
_LOGGER = logging.getLogger(__name__)
async def apply_cover(hass, config: dict, snapshot, decision) -> bool:
    if decision.cover_action not in (ACTION_CLOSE, ACTION_OPEN):
        return True
    ok = True
    for entity_id in as_list(config.get(CONF_BLINDS)):
        ok = await _apply_one(hass, entity_id, decision) and ok
    return ok
async def _apply_one(hass, entity_id, decision) -> bool:
    state = controllable(hass, entity_id, ("unavailable", "unknown", "opening", "closing"))
    if state is None:
        return True
    assumed = is_assumed(state)
    opening = decision.cover_action == ACTION_OPEN
    if not assumed:
        if opening and state.state == "open":
            return True
        if not opening and state.state == "closed":
            return True
    feats = cover_features(state)
    try:
        if feats.open_close:
            await hass.services.async_call("cover", "open_cover" if opening else "close_cover", {ATTR_ENTITY_ID: entity_id}, blocking=True)
        elif feats.set_position:
            await hass.services.async_call("cover", "set_cover_position", {ATTR_ENTITY_ID: entity_id, "position": 100 if opening else 0}, blocking=True)
        else:
            _LOGGER.debug("Cover %s exposes no open/close or position control; skipping", entity_id)
        return True
    except Exception:
        _LOGGER.exception("Failed to apply cover decision to %s", entity_id)
        return False

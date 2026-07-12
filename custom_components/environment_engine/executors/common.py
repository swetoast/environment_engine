"""Shared helpers for actuator executors (KISS/DRY: one guard, one speed map)."""
from __future__ import annotations

SPEED_TO_PERCENTAGE = {"low": 33, "medium": 66, "high": 100}
_SKIP = ("unavailable", "unknown")


def controllable(hass, entity_id, skip=_SKIP):
    """Live state for a configured entity, or None when there's nothing to do
    (unset, missing, or in a skip state). Callers treat None as success/no-op."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in skip:
        return None
    return state


def is_assumed(state) -> bool:
    # Assumed-state (e.g. IR) devices don't report back, so we never trust their
    # perceived state to skip a command.
    return bool(state.attributes.get("assumed_state", False))

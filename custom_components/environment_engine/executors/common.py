"""Shared helpers for actuator executors (KISS/DRY: one guard, one speed map)."""
from __future__ import annotations

SPEED_TO_PERCENTAGE = {"low": 33, "medium": 66, "high": 100}


def snap_percentage(pct, step):
    """Round a tier percentage onto a device's own speed grid.

    A three-speed unit reports percentage_step 33.33, so its real settings are 33 / 67 /
    100 -- but the tier table has medium at 66. Sending a value the device actually offers
    is cleaner than relying on Home Assistant to round it, and matches the medium tier to
    the device's true middle speed rather than one point below it. An unreported or absurd
    step leaves the value untouched.
    """
    try:
        step = float(step)
    except (TypeError, ValueError):
        return pct
    if step <= 0 or step >= 100:
        return pct
    snapped = round(round(pct / step) * step)
    return max(int(step + 0.5), min(100, snapped))
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

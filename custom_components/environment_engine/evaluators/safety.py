from __future__ import annotations
from dataclasses import dataclass
@dataclass(slots=True)
class SafetyResult:
    blocked: bool
    hvac_mode: str | None
    reason: str


def evaluate_safety(snapshot, capabilities, options) -> SafetyResult:
    if capabilities.smoke and snapshot.smoke_detected:
        return SafetyResult(True, "off", "smoke detected")
    if capabilities.outlet_overload and snapshot.outlet_overloaded:
        return SafetyResult(True, "off", "outlet overload detected")
    if capabilities.lightning and snapshot.lightning_hold:
        # For the AC there is no advisory tier: any active hold stops the compressor. The band
        # only labels how close the storm is; it does not decide whether to block.
        strikes = snapshot.lightning_strikes
        closest = round(snapshot.lightning_closest) if snapshot.lightning_closest is not None else "?"
        return SafetyResult(True, "off", f"lightning within {closest} km ({strikes} strike{'s' if strikes != 1 else ''})")
    return SafetyResult(False, None, "no safety block")

from __future__ import annotations
from .climate import apply_climate
from .cover import apply_cover
from .fan import apply_fan
from .humidifier import apply_humidifier
from .ionizer import apply_ionizer
from .ventilation import apply_ventilation
from .purifier import apply_purifier


class EnvironmentExecutor:
    """Sends a decision to the devices, one independent channel per actuator.

    Each channel remembers the last command it delivered and is only re-applied when ITS
    part of the decision changes. The earlier version kept a single signature for the
    whole decision, so a change on any one device re-ran every executor: the fan starting
    re-asserted the purifier's state (and the other way round), which undid anything set
    by hand on a device the decision had not changed for. A channel whose device was not
    reachable is left uncached, so it is retried on the next cycle instead of dropped.
    """

    def __init__(self, hass, config: dict) -> None:
        self.hass = hass
        self.config = config
        self._sent: dict[str, tuple] = {}

    def _channels(self, snapshot, d):
        hass, config = self.hass, self.config
        return (
            ("climate", (d.hvac_mode, d.target_temperature), lambda: apply_climate(hass, config, snapshot, d)),
            ("fan", (d.fan_action, d.fan_speed), lambda: apply_fan(hass, config, snapshot, d)),
            ("cover", (d.cover_action,), lambda: apply_cover(hass, config, snapshot, d)),
            ("purifier", (d.purifier_action, d.purifier_speed), lambda: apply_purifier(hass, config, d)),
            ("humidifier", (d.humidifier_action, d.humidifier_target), lambda: apply_humidifier(hass, config, snapshot, d)),
            ("ionizer", (d.ionizer_action,), lambda: apply_ionizer(hass, config, d)),
            ("ventilation", (d.ventilation_action,), lambda: apply_ventilation(hass, config, d)),
        )

    async def apply(self, snapshot, decision, force: bool = False) -> None:
        """Apply the decision. `force` (the Apply Decision button) and a safety block both
        bypass the per-channel memory and re-assert every channel."""
        for name, signature, send in self._channels(snapshot, decision):
            if not force and not decision.blocked and self._sent.get(name) == signature:
                continue
            if await send():
                self._sent[name] = signature
            else:
                self._sent.pop(name, None)

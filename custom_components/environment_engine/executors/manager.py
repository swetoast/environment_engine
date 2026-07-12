from __future__ import annotations
from .climate import apply_climate
from .cover import apply_cover
from .fan import apply_fan
from .humidifier import apply_humidifier
from .ionizer import apply_ionizer
from .ventilation import apply_ventilation
from .purifier import apply_purifier
class EnvironmentExecutor:
    def __init__(self, hass, config: dict) -> None:
        self.hass = hass
        self.config = config
        self.last_signature: tuple | None = None
    async def apply(self, snapshot, decision) -> None:
        signature = decision.signature()
        if signature == self.last_signature and not decision.blocked:
            return
        results = [
            await apply_climate(self.hass, self.config, snapshot, decision),
            await apply_fan(self.hass, self.config, snapshot, decision),
            await apply_cover(self.hass, self.config, snapshot, decision),
            await apply_purifier(self.hass, self.config, decision),
            await apply_humidifier(self.hass, self.config, snapshot, decision),
            await apply_ionizer(self.hass, self.config, decision),
            await apply_ventilation(self.hass, self.config, decision),
        ]
        # Only cache the signature if every actuator succeeded; a swallowed
        # failure leaves the cache clear so the next cycle retries.
        self.last_signature = signature if all(results) else None

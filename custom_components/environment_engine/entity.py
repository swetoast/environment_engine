from __future__ import annotations
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, MANUFACTURER


class EnvironmentEngineEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def device_info(self):
        title = self.entry.title or "Environment Engine"
        # Device name carries the room so entity_ids become
        # <domain>.<room>_environment_engine_<function>.
        name = title if "environment engine" in title.lower() else f"{title} Environment Engine"
        return {"identifiers": {(DOMAIN, self.entry.entry_id)}, "name": name, "manufacturer": MANUFACTURER}

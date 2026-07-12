from __future__ import annotations
from dataclasses import asdict, is_dataclass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN
def _dump(obj):
    if obj is None:
        return None
    if is_dataclass(obj):
        return asdict(obj)
    return obj
async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    data = coordinator.data or {}
    return {"entry_data": dict(entry.data), "entry_options": dict(entry.options), "decision": _dump(data.get("decision")), "raw_decision": _dump(data.get("raw_decision")), "snapshot": _dump(data.get("snapshot")), "evaluations": {name: _dump(result) for name, result in data.get("evaluations", {}).items()}, "capabilities": _dump(data.get("capabilities")), "learning": _dump(data.get("learning"))}

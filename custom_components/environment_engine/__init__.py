from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_GLOBAL, ENTRY_ROOM, PLATFORMS
from .coordinator import EnvironmentCoordinator


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # v1 entries predate the global/room split -> treat them as standalone rooms.
    if entry.version < 2:
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_ENTRY_TYPE: ENTRY_ROOM}, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_GLOBAL:
        # Shared outdoor/energy config only -- no coordinator or entities of its own.
        # When it changes, reload the rooms so they pick up the new global values.
        entry.async_on_unload(entry.add_update_listener(_reload_rooms))
        return True
    coordinator = EnvironmentCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_GLOBAL:
        return True
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")
    if coordinator is not None:
        coordinator.unload()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


async def _reload_rooms(hass: HomeAssistant, entry: ConfigEntry) -> None:
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.data.get(CONF_ENTRY_TYPE) == ENTRY_ROOM and other.state.recoverable:
            await hass.config_entries.async_reload(other.entry_id)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

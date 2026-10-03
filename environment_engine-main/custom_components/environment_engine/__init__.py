from __future__ import annotations
import logging
import os
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_GLOBAL, ENTRY_ROOM, PLATFORMS
from .coordinator import EnvironmentCoordinator

_LOGGER = logging.getLogger(__name__)


def _sweep_orphaned_bytecode() -> None:
    """Delete cached .pyc files whose source module no longer exists.

    When a module is renamed or moved (e.g. air_quality.py -> evaluators/air_quality.py),
    Home Assistant can keep loading the stale __pycache__ entry from the old location, which
    then fails with 'No module named ...' on the old import path. Python won't clean these up
    on its own because nothing imports them anymore. We remove any orphaned .pyc so a rename
    can never leave a ghost module behind.
    """
    root = os.path.dirname(__file__)
    for dirpath, dirnames, filenames in os.walk(root):
        if os.path.basename(dirpath) != "__pycache__":
            continue
        source_dir = os.path.dirname(dirpath)
        for name in filenames:
            if not name.endswith(".pyc"):
                continue
            module = name.split(".", 1)[0]  # 'air_quality.cpython-312.pyc' -> 'air_quality'
            if not os.path.exists(os.path.join(source_dir, f"{module}.py")):
                try:
                    os.remove(os.path.join(dirpath, name))
                    _LOGGER.debug("Removed orphaned bytecode %s", name)
                except OSError:
                    pass


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    await hass.async_add_executor_job(_sweep_orphaned_bytecode)
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
    await coordinator.async_load_model()  # pick up what this room taught us before the restart
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

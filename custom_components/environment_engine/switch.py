from __future__ import annotations
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoreEntity
from .const import DOMAIN, OPT_AUTO_APPLY
from .entity import EnvironmentEngineEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [AutoApplySwitch(coordinator, entry)]
    if coordinator.options.portable_ac:
        entities.append(ExhaustVentedSwitch(coordinator, entry))
    async_add_entities(entities)


class AutoApplySwitch(EnvironmentEngineEntity, SwitchEntity):
    _attr_name = "Auto Apply"
    _attr_icon = "mdi:auto-mode"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "auto_apply")

    @property
    def is_on(self):
        return bool(self.coordinator.options.auto_apply)

    async def async_turn_on(self, **kwargs) -> None:
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, OPT_AUTO_APPLY: True})

    async def async_turn_off(self, **kwargs) -> None:
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, OPT_AUTO_APPLY: False})


class ExhaustVentedSwitch(EnvironmentEngineEntity, SwitchEntity, RestoreEntity):
    """Manual 'the portable AC's exhaust is vented' override for rooms without a
    contact sensor on the vent window. Fails closed and auto-reverts after a
    timeout so a forgotten toggle can't strand the engine into venting hot air."""
    _attr_name = "Exhaust Vented"
    _attr_icon = "mdi:window-open-variant"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "exhaust_vented")
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == "on":
            self.coordinator.vent_override = True
            self._schedule_revert()

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_revert()

    @property
    def is_on(self):
        return self.coordinator.vent_override

    @property
    def extra_state_attributes(self):
        return {"auto_revert_hours": self.coordinator.options.vent_revert}

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.vent_override = True
        self._schedule_revert()
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        self._cancel_revert()
        self.coordinator.vent_override = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    def _schedule_revert(self) -> None:
        self._cancel_revert()
        hours = self.coordinator.options.vent_revert
        if hours > 0:
            self._unsub = async_call_later(self.hass, hours * 3600, self._revert)

    def _cancel_revert(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def _revert(self, _now=None) -> None:
        self._unsub = None
        self.coordinator.vent_override = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

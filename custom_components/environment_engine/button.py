from __future__ import annotations
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .entity import EnvironmentEngineEntity
async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ApplyDecisionButton(coordinator, entry), RefreshDecisionButton(coordinator, entry), ResetLearningButton(coordinator, entry)])
class ApplyDecisionButton(EnvironmentEngineEntity, ButtonEntity):
    _attr_name = "Apply Decision"
    _attr_icon = "mdi:play"
    _attr_entity_category = EntityCategory.CONFIG
    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "apply_decision")
    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None and not self.coordinator.data["decision"].blocked
    async def async_press(self) -> None:
        await self.coordinator.async_apply_decision()
class RefreshDecisionButton(EnvironmentEngineEntity, ButtonEntity):
    _attr_name = "Refresh Decision"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "refresh_decision")
    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
class ResetLearningButton(EnvironmentEngineEntity, ButtonEntity):
    _attr_name = "Reset Learning"
    _attr_icon = "mdi:brain"
    _attr_entity_category = EntityCategory.CONFIG
    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "reset_learning")
    async def async_press(self) -> None:
        self.coordinator.reset_learning()
        await self.coordinator.async_request_refresh()

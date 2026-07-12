from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .entity import EnvironmentEngineEntity
async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([EnvironmentBlockedSensor(coordinator, entry), EnvironmentInvalidEntitiesSensor(coordinator, entry), EnvironmentFilterDueSensor(coordinator, entry), EnvironmentStrugglingSensor(coordinator, entry)])
class EnvironmentBlockedSensor(EnvironmentEngineEntity, BinarySensorEntity):
    _attr_name = "Blocked"
    _attr_icon = "mdi:shield-alert"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "blocked")
    @property
    def is_on(self):
        return bool(self.coordinator.data["decision"].blocked)
class EnvironmentInvalidEntitiesSensor(EnvironmentEngineEntity, BinarySensorEntity):
    _attr_name = "Invalid Entities"
    _attr_icon = "mdi:alert-circle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "invalid_entities")
    @property
    def is_on(self):
        return bool(self.coordinator.data["snapshot"].invalid_entities)
    @property
    def extra_state_attributes(self):
        return {"entities": self.coordinator.data["snapshot"].invalid_entities}


class EnvironmentFilterDueSensor(EnvironmentEngineEntity, BinarySensorEntity):
    """On when purifier runtime reaches the configured filter life (0 = disabled)."""
    _attr_name = "Filter Due"
    _attr_icon = "mdi:air-filter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "filter_due")

    @property
    def is_on(self):
        life = self.coordinator.options.filter_life
        return life > 0 and self.coordinator.data["runtime"]["purifier"] >= life

    @property
    def extra_state_attributes(self):
        return {"filter_used_hours": round(self.coordinator.data["runtime"]["purifier"], 1), "filter_life_hours": self.coordinator.options.filter_life}


class EnvironmentStrugglingSensor(EnvironmentEngineEntity, BinarySensorEntity):
    """On when the AC runs but the room keeps gaining heat -- the model has measured that
    cooling isn't winning. Usually a door or window left open, a dirty filter, an
    undersized unit, or simply an extreme day. Worth a look rather than a silent battle."""
    _attr_name = "Struggling To Cool"
    _attr_icon = "mdi:snowflake-alert"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "struggling")

    @property
    def is_on(self):
        model = self.coordinator.thermal
        return bool(model.struggling and model.confidence > 0)

    @property
    def extra_state_attributes(self):
        model = self.coordinator.thermal
        return {
            "ac_removes_c_per_hour": round(-model.cooling_power * 60, 2),
            "cooling_effectiveness_pct": round(model.effectiveness * 100),
            "measured_by_outdoor_band": {band: round(rate * 60, 2) for band, rate in model.cooling_effect.items()},
        }

from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .entity import EnvironmentEngineEntity
async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([EnvironmentBlockedSensor(coordinator, entry), EnvironmentInvalidEntitiesSensor(coordinator, entry), EnvironmentFilterDueSensor(coordinator, entry), EnvironmentStrugglingSensor(coordinator, entry), EnvironmentUnexplainedHeatSensor(coordinator, entry)])
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
        health = self.coordinator.air.filter_health
        if health is not None and health < 0.5:
            return True  # measured: it has lost half its cleaning power, whatever the clock says
        life = self.coordinator.options.filter_life
        return life > 0 and self.coordinator.data["runtime"]["purifier"] >= life

    @property
    def extra_state_attributes(self):
        health = self.coordinator.air.filter_health
        attrs = {
            "filter_used_hours": round(self.coordinator.data["runtime"]["purifier"], 1),
            "filter_life_hours": self.coordinator.options.filter_life,
        }
        if health is not None:
            attrs["filter_health_pct"] = round(health * 100)
            attrs["measured_clean_rate"] = round(self.coordinator.air.clean_rate, 4)
        return attrs


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


class EnvironmentUnexplainedHeatSensor(EnvironmentEngineEntity, BinarySensorEntity):
    """On when the room is gaining (or losing) heat that the learned model cannot account for.

    The model already explains the outdoors, the sun, the AC and you. A persistent, one-sided
    error means something real that nobody told the engine about: a window cracked open, a door
    left ajar, an oven running, a radiator that came on -- or a temperature sensor quietly
    drifting out of calibration.
    """
    _attr_name = "Unexplained Heat"
    _attr_icon = "mdi:home-alert-outline"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "unexplained_heat")

    @property
    def is_on(self):
        return self.coordinator.thermal.anomaly() is not None

    @property
    def extra_state_attributes(self):
        model = self.coordinator.thermal
        return {
            "direction": model.anomaly() or "none",
            "unexplained_c_per_hour": round(model.unexplained_drift * 60, 2),
            "how_unusual": round(model.anomaly_score, 1),
        }

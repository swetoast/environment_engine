from __future__ import annotations
import dataclasses
from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .entity import EnvironmentEngineEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([EnvironmentDecisionSensor(coordinator, entry), EnvironmentThermalPressureSensor(coordinator, entry),
                        EnvironmentRuntimeSensor(coordinator, entry, "climate", "Air Conditioner Used Today"),
                        EnvironmentRuntimeSensor(coordinator, entry, "purifier", "Air Purifier Used Today"),
                        EnvironmentDiagnosticsSensor(coordinator, entry)])


def _ac_summary(decision):
    mode = decision.hvac_mode
    if mode is None:
        return "not adjusting"
    if mode == "off":
        return "off"
    if mode == "cool":
        return f"cooling to {decision.target_temperature}°C" if decision.target_temperature is not None else "cooling"
    if mode == "dry":
        return "drying"
    if mode == "fan_only":
        return "fan only"
    return mode


def _onoff(action, speed=None):
    if action in (None, "none", "off"):
        return "off"
    if action == "on":
        return speed or "on"
    return action


def _price_level(rank):
    if rank is None:
        return None
    return "cheap" if rank <= 0.33 else "expensive" if rank >= 0.66 else "moderate"


class EnvironmentDecisionSensor(EnvironmentEngineEntity, SensorEntity):
    _attr_name = "Decision"
    _attr_icon = "mdi:home-thermometer-outline"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "decision")

    @property
    def native_value(self):
        return self.coordinator.data["decision"].strategy

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        d, c, s = data["decision"], data["capabilities"], data["snapshot"]
        t = data["evaluations"].get("target")
        # What the engine is doing and why -- only devices that exist, plain language.
        attrs = {"reason": d.reason, "confidence_pct": round(d.confidence * 100)}
        if c.climate:
            attrs["air_conditioner"] = _ac_summary(d)
        if c.fan:
            attrs["fan"] = _onoff(d.fan_action, d.fan_speed)
        if c.blinds:
            attrs["blinds"] = _onoff(d.cover_action)
        if c.purifier:
            attrs["air_purifier"] = _onoff(d.purifier_action, d.purifier_speed)
        if c.ionizer:
            attrs["ionizer"] = _onoff(d.ionizer_action)
        if c.ventilation:
            attrs["ventilation"] = _onoff(d.ventilation_action)
        if c.humidifier:
            hum = _onoff(d.humidifier_action)
            attrs["humidifier"] = f"{hum} (target {d.humidifier_target}%)" if d.humidifier_target is not None else hum
        # A little context that helps the number make sense.
        if t is not None:
            attrs["comfort_target_c"] = t.effective_target
        if s.feels_like is not None:
            attrs["feels_like_c"] = round(s.feels_like, 1)
        aq = data["evaluations"].get("air_quality")
        if c.air_quality and aq is not None and getattr(aq, "dominant", None):
            attrs["main_pollutant"] = aq.dominant
        level = _price_level(s.price_rank)
        if c.pricing and level is not None:
            attrs["power_price"] = level
        if d.blocked:
            attrs["safety_hold"] = True
        return attrs


class EnvironmentDiagnosticsSensor(EnvironmentEngineEntity, SensorEntity):
    """Engine internals for debugging -- capabilities, learning counters, price and
    lightning detail. Diagnostic category so it stays out of the way."""
    _attr_name = "Diagnostics"
    _attr_icon = "mdi:cog-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "diagnostics")

    @property
    def native_value(self):
        return self.coordinator.data["raw_decision"].strategy

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        r, s, l, c = data["raw_decision"], data["snapshot"], data["learning"], data["capabilities"]
        attrs = {
            "raw_strategy": r.strategy,
            "price_rank": round(s.price_rank, 2) if s.price_rank is not None else None,
            "price_precool_window": s.price_precool,
            "lightning_hold": s.lightning_hold,
            "lightning_strikes": s.lightning_strikes,
            "lightning_closest_km": round(s.lightning_closest, 1) if s.lightning_closest is not None else None,
            "drying_successes": l.drying_successes,
            "drying_failures": l.drying_failures,
            "model_samples": self.coordinator.thermal.samples,
            "model_samples_rejected": self.coordinator.thermal.rejected,
            "cooling_effectiveness_pct": round(self.coordinator.thermal.effectiveness * 100),
            "cooling_bias": round(self.coordinator.thermal.cooling_bias(), 3),
            "invalid_entities": s.invalid_entities,
        }
        attrs.update({f"has_{field.name}": getattr(c, field.name) for field in dataclasses.fields(c)})
        return attrs


class EnvironmentThermalPressureSensor(EnvironmentEngineEntity, SensorEntity):
    """How strongly the room is asking to be cooled, 0-100%. The attributes explain
    where that number comes from: the target it's aiming at, how fast the room gains
    and sheds heat, and what the weather is about to do."""
    _attr_name = "Cooling Demand"
    _attr_icon = "mdi:thermometer-alert"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "thermal_pressure")

    @property
    def native_value(self):
        return round(self.coordinator.data["evaluations"]["thermal"].pressure * 100)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        s, m, model = data["snapshot"], data["memory"], self.coordinator.thermal
        t = data["evaluations"].get("target")
        attrs = {}
        if t is not None:
            attrs["comfort_target_c"] = t.base_target
            attrs["cooling_to_c"] = t.effective_target
            if t.precool:
                attrs["precooling_by_c"] = round(t.precool, 1)
        if s.feels_like is not None:
            attrs["feels_like_c"] = round(s.feels_like, 1)
        if t is not None and t.cooling_drop:
            attrs["target_lowered_by_c"] = t.cooling_drop
        if t is not None and t.relaxation:
            attrs["target_eased_by_c"] = t.relaxation
        if t is not None and (t.limited_by_min or t.limited_by_max):
            attrs["target_limited_by_device"] = "minimum" if t.limited_by_min else "maximum"
        attrs["room_holds_heat_pct"] = round(m.thermal_inertia * 100)
        attrs["expected_warming_c"] = round(self.coordinator._anticipation(s), 1)
        # What the learned thermal model knows about this room.
        solar = self.coordinator._solar_proxy(s)
        predicted = model.predict(s.indoor_temp, s.outdoor_temp, solar, minutes=30, occupied=bool(s.occupancy))
        if predicted is not None:
            attrs["predicted_in_30min_c"] = round(predicted, 1)
        tau = model.time_constant
        if tau is not None:
            attrs["room_time_constant_h"] = round(tau / 60.0, 1)
        attrs["model_confidence_pct"] = round(model.confidence * 100)
        if model.confidence > 0:
            attrs["heat_leaks_in_c_per_hour"] = round(model.leakiness * 60, 2)
            attrs["sun_adds_c_per_hour"] = round(model.solar_gain * 60, 2)
            attrs["ac_removes_c_per_hour"] = round(-model.cooling_power * 60, 2)
            attrs["you_add_c_per_hour"] = round(model.occupied_gain * 60, 2)
        if model.struggling:
            attrs["struggling_to_cool"] = True
        if s.forecast_high is not None:
            attrs["forecast_high_c"] = s.forecast_high
        attrs["incoming_heat_pct"] = round(s.forecast_pressure * 100)
        return attrs


class EnvironmentRuntimeSensor(EnvironmentEngineEntity, RestoreSensor):
    """How long the device has run today (hours), rolling over at local midnight.
    The lifetime total rides along as an attribute so the filter counter -- and today's
    partial usage -- both survive a restart."""
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "h"
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator, entry, channel, name) -> None:
        super().__init__(coordinator, entry, f"runtime_{channel}")
        self._channel = channel
        self._attr_name = name

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None:
            return
        attrs = last.attributes or {}
        try:  # lifetime total always restores (filter life must not reset)
            self.coordinator.runtime.seed(self._channel, float(attrs["total_hours"]))
        except (KeyError, TypeError, ValueError):
            pass
        try:  # today's usage restores only if it was recorded today
            self.coordinator.runtime.seed_today(self._channel, float(last.state), str(attrs["day"]))
        except (KeyError, TypeError, ValueError):
            pass

    @property
    def native_value(self):
        return round(self.coordinator.runtime.today_hours(self._channel), 2)

    @property
    def extra_state_attributes(self):
        return {
            "total_hours": round(self.coordinator.runtime.hours(self._channel), 2),
            "day": self.coordinator.runtime.day,
        }

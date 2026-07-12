from __future__ import annotations
from .const import (
    ACTION_NONE, ACTION_OFF, HVAC_COOL, HVAC_DRY, HVAC_FAN_ONLY, HVAC_OFF,
    STRATEGY_AIR_CIRCULATION,
    STRATEGY_QUIET_COOLING, STRATEGY_AIR_QUALITY, STRATEGY_AWAY_IDLE, STRATEGY_CLIMATE_OFFLINE,
    STRATEGY_COOLING, STRATEGY_DEHUMIDIFY, STRATEGY_HUMIDIFY, STRATEGY_IDLE, STRATEGY_MOLD_PREVENTION,
    STRATEGY_PASSIVE_VENTILATION, STRATEGY_SAFETY_STOP, STRATEGY_SOLAR_MITIGATION,
)
from .decision import Decision
from .evaluators import drying_pressure
from .resolvers import resolve_climate, resolve_cover, resolve_fan, resolve_humidifier, resolve_purifier, resolve_ventilation

# Headline label priority when several actuators act at once. This is only a
# human-facing summary; every actuator is decided independently regardless of it.
_LABEL_PRIORITY = [STRATEGY_COOLING, STRATEGY_DEHUMIDIFY, STRATEGY_HUMIDIFY, STRATEGY_PASSIVE_VENTILATION, STRATEGY_QUIET_COOLING, STRATEGY_AIR_CIRCULATION, STRATEGY_MOLD_PREVENTION, STRATEGY_AIR_QUALITY, STRATEGY_SOLAR_MITIGATION]
_MANAGED = {HVAC_COOL, HVAC_DRY, HVAC_FAN_ONLY}


class Planner:
    """Composes one Decision from four independent actuator resolvers.

    No actuator is privileged: climate, fan, cover, and purifier are each
    resolved from the environmental pressures and gated only on their own
    capability, then merged. The engine does the most useful thing with whatever
    devices exist -- one AC per room, a lone fan, a lone purifier, or any mix.
    """

    def __init__(self, capabilities, options) -> None:
        self.capabilities = capabilities
        self.options = options

    def plan(self, snapshot, evaluations) -> Decision:
        safety = evaluations["safety"]
        if safety.blocked:
            return Decision(STRATEGY_SAFETY_STOP, safety.hvac_mode or HVAC_OFF, None, ACTION_OFF, None, ACTION_NONE, ACTION_NONE, 1.0, safety.reason, True)
        if not snapshot.occupancy:
            return self._away(snapshot)

        passive_cooling = (
            self.capabilities.windows
            and snapshot.window_open
            and snapshot.outdoor_temp is not None
            and snapshot.outdoor_temp < snapshot.indoor_temp
            and not evaluations["air_quality"].seal  # don't invite in bad outdoor air
            and not self.options.portable_ac  # a portable AC's window is its exhaust vent
        )

        sleep = not snapshot.sun_up and snapshot.dark  # genuinely dark night
        hvac_mode, target, climate_driver = resolve_climate(snapshot, self.capabilities, self.options, evaluations, passive_cooling)
        fan_action, fan_speed, fan_driver = resolve_fan(snapshot, self.capabilities, self.options, evaluations, passive_cooling, sleep)
        cover_action, cover_driver = resolve_cover(snapshot, self.capabilities, evaluations)
        purifier_action, purifier_speed, ionizer_action, purifier_driver = resolve_purifier(self.capabilities, self.options, evaluations, sleep)
        humidifier_action, humidifier_target, humidifier_driver = resolve_humidifier(snapshot, self.capabilities, self.options, evaluations)
        ventilation_action, ventilation_driver = resolve_ventilation(snapshot, self.capabilities, self.options, evaluations)

        drivers = {d for d in (climate_driver, fan_driver, cover_driver, purifier_driver, humidifier_driver, ventilation_driver) if d}
        strategy = self._label(drivers, snapshot)
        confidence, reason = self._summary(strategy, evaluations)
        return Decision(strategy, hvac_mode, target, fan_action, fan_speed, cover_action, purifier_action, confidence, reason, humidifier_action=humidifier_action, humidifier_target=humidifier_target, purifier_speed=purifier_speed, ionizer_action=ionizer_action, ventilation_action=ventilation_action)

    def _away(self, snapshot) -> Decision:
        managed = self.capabilities.climate and snapshot.climate_valid and snapshot.hvac_mode in _MANAGED
        hvac = HVAC_OFF if managed else None
        fan = ACTION_OFF if self.capabilities.fan else ACTION_NONE
        vent = ACTION_OFF if self.capabilities.ventilation else ACTION_NONE
        return Decision(STRATEGY_AWAY_IDLE, hvac, None, fan, None, ACTION_NONE, ACTION_NONE, 1.0, "home is unoccupied", ventilation_action=vent)

    def _label(self, drivers, snapshot) -> str:
        for driver in _LABEL_PRIORITY:
            if driver in drivers:
                return driver
        if self.capabilities.climate and not snapshot.climate_valid:
            return STRATEGY_CLIMATE_OFFLINE
        return STRATEGY_IDLE

    def _summary(self, strategy, ev):
        table = {
            STRATEGY_COOLING: (ev["thermal"].confidence, ev["thermal"].reason),
            STRATEGY_AIR_CIRCULATION: (ev["thermal"].confidence, "circulating air to ease heat"),
            STRATEGY_QUIET_COOLING: (ev["thermal"].confidence, "quiet hours: moving air instead of running the compressor"),
            STRATEGY_PASSIVE_VENTILATION: (ev["thermal"].confidence, "window ventilation can reduce heat"),
            STRATEGY_DEHUMIDIFY: (drying_pressure(ev), ev["humidity"].reason),
            STRATEGY_HUMIDIFY: (ev["humidity"].confidence, "air is dry; adding moisture"),
            STRATEGY_MOLD_PREVENTION: (ev["mold"].risk, ev["mold"].reason),
            STRATEGY_AIR_QUALITY: (ev["air_quality"].pressure, ev["air_quality"].reason),
            STRATEGY_SOLAR_MITIGATION: (ev["solar"].pressure, ev["solar"].reason),
        }
        if strategy in table:
            confidence, reason = table[strategy]
            return round(float(confidence), 4), reason
        if strategy == STRATEGY_CLIMATE_OFFLINE:
            return 0.0, "climate entity unavailable; managing other devices"
        return 0.0, "no environmental action needed"

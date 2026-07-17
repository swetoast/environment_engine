from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from .adaptive_learning import AdaptiveLearning
from .air_model import AirModel, speed_fraction
from .thermal_model import ThermalModel
from .capabilities import build_capabilities
from .const import CONF_AQI, CONF_BLINDS, CONF_ENTRY_TYPE, ENTRY_GLOBAL, ENTRY_ROOM, CONF_CLIMATE, CONF_CO2, CONF_FORECAST_HIGH, CONF_HUMIDIFIER, CONF_HUMIDITY, CONF_LIGHTNING_DISTANCE, CONF_LUX, CONF_OCCUPANCY, CONF_OUTDOOR_AQI, CONF_OUTLET_OVERLOAD, CONF_PM10, CONF_PM25, CONF_PRICE, CONF_PRICE_AVERAGE, CONF_PRICE_FORECAST, CONF_PURIFIER, CONF_SMOKE, CONF_TEMPERATURE, CONF_VOC, CONF_WEATHER, CONF_WINDOW, CONF_VENT, DOMAIN, ENTITY_KEYS, HVAC_COOL, HVAC_DRY, HVAC_FAN_ONLY
from .entities import as_list
from .evaluators import evaluate_air_quality, evaluate_energy, evaluate_humidity, evaluate_mold, evaluate_safety, evaluate_solar, evaluate_thermal
from .executors import EnvironmentExecutor
from .forecast import heat_outlook, upcoming_peak
from .hysteresis import HysteresisEngine
from dataclasses import replace as _dc_replace
from .decay import PeakDecay
from .lightning import lightning_band, lightning_hold
from .options import build_options, resolved_options
from .const import PRICING_SPOT as _PRICING_SPOT
from .price import day_values, in_cheapest_window, price_rank as _price_rank, price_series
from .psychrometrics import feels_like as _feels_like
from .quiet_hours import in_quiet_hours
from .runtime import RuntimeTracker
from .planner import Planner
from .snapshot import Snapshot
from .target_resolver import resolve_effective_target
from .thermal_memory import ThermalMemoryEngine
from .units import to_celsius
_LOGGER = logging.getLogger(__name__)
_UNSET = ("unknown", "unavailable", "")
_MANAGED = {HVAC_COOL, HVAC_DRY, HVAC_FAN_ONLY}


class EnvironmentCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass, entry) -> None:
        self.hass = hass  # needed by _refresh_config -> _global_entry before super().__init__
        self.entry = entry
        self._refresh_config()
        self.memory_engine = ThermalMemoryEngine()
        self.hysteresis = HysteresisEngine()
        self.learning = AdaptiveLearning()
        self.thermal = ThermalModel()
        self.air = AirModel()
        self._model_store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.thermal")
        self._last_update_ts = None
        self.aq_memory = PeakDecay()
        self.seal_memory = PeakDecay()
        self.presence_memory = PeakDecay()
        self.runtime = RuntimeTracker()
        self.vent_override = False  # manual portable-AC exhaust-vented toggle
        self.executor = EnvironmentExecutor(hass, self.config)
        self.previous_snapshot = None
        self.previous_decision = None
        self._auto_apply_pending = False
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=self.options.update_interval), config_entry=entry)
        self._remove_auto_apply_listener = self.async_add_listener(self._handle_update_finished)

    def _refresh_config(self) -> None:
        data = dict(self.entry.data)
        options = dict(self.entry.options)
        if self.entry.data.get(CONF_ENTRY_TYPE) == ENTRY_ROOM:
            shared = self._global_entry()
            if shared is not None:
                data = {**shared.data, **data}        # room overrides global on conflict
                options = {**shared.options, **options}
        self.config = build_options(data, options)
        self.options = resolved_options(data, options)
        self.capabilities = build_capabilities(self.config)

    def _global_entry(self):
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_GLOBAL:
                return entry
        return None

    async def _async_update_data(self) -> dict[str, Any]:
        self._refresh_config()
        self.executor.config = self.config
        snapshot = self._snapshot()
        self.learning.update(self.previous_snapshot, self.previous_decision, snapshot)
        _now_ts = dt_util.utcnow().timestamp()
        _dt_min = (_now_ts - self._last_update_ts) / 60.0 if self._last_update_ts is not None else 0.0
        self._last_update_ts = _now_ts
        was_cooling = getattr(self.previous_decision, "hvac_mode", None) in (HVAC_COOL, HVAC_DRY)
        learned = self.thermal.update(self.previous_snapshot, snapshot, _dt_min, was_cooling, self._solar_proxy(self.previous_snapshot))
        previous = self.previous_decision
        purifier_speed = speed_fraction(getattr(previous, "purifier_action", None), getattr(previous, "purifier_speed", None))
        learned |= self.air.update(self.previous_snapshot, snapshot, _dt_min, purifier_speed)
        if learned:
            self._save_model()
        memory = self.memory_engine.update(snapshot.indoor_temp, snapshot.humidity, snapshot.outdoor_temp)
        evaluations = self._evaluate(snapshot, memory)
        raw_decision = Planner(self.capabilities, self.options).plan(snapshot, evaluations)
        decision = self.hysteresis.apply(raw_decision, self.options.min_change_interval, self.options.compressor_min_cycle, self.options.device_min_cycle)
        self.previous_snapshot = snapshot
        self.previous_decision = decision
        active = set()
        if any(st.state in ("cool", "dry", "fan_only", "heat") for st in self._usable(self._states(CONF_CLIMATE))):
            active.add("climate")
        if any(st.state == "on" for st in self._states(CONF_PURIFIER)):
            active.add("purifier")
        self.runtime.update(dt_util.utcnow().timestamp(), active, dt_util.now().date().isoformat())
        self._auto_apply_pending = bool(self.options.auto_apply)
        return {"snapshot": snapshot, "memory": memory, "evaluations": evaluations, "decision": decision, "raw_decision": raw_decision, "capabilities": self.capabilities, "learning": self.learning.state, "runtime": {"climate": self.runtime.hours("climate"), "purifier": self.runtime.hours("purifier")}, "runtime_today": {"climate": self.runtime.today_hours("climate"), "purifier": self.runtime.today_hours("purifier")}}

    def _handle_update_finished(self) -> None:
        if self._auto_apply_pending and self.data:
            self._auto_apply_pending = False
            self.hass.async_create_task(self.async_apply_decision())

    def _evaluate(self, snapshot: Snapshot, memory) -> dict[str, Any]:
        solar = evaluate_solar(snapshot, self.options)
        energy = evaluate_energy(snapshot, self.options)
        humidity = evaluate_humidity(snapshot, memory, self.learning.drying_bias())
        mold = evaluate_mold(snapshot, memory)
        air_quality = evaluate_air_quality(snapshot, self.options)
        now = dt_util.utcnow().timestamp()
        half_life = self.options.air_recovery * 60
        held = self.aq_memory.update(air_quality.pressure, now, half_life)
        if held > air_quality.pressure + 0.01:  # keep purifying through the tail of a spike
            air_quality = _dc_replace(air_quality, pressure=held, purifier_recommended=True, reason="clearing the air after a particle event")
        # Seal hold: once an outdoor event seals the room, keep it sealed through a
        # lull (decaying) so it doesn't flap around the threshold. New highs re-tighten.
        held_outdoor = self.seal_memory.update(snapshot.outdoor_aqi or 0.0, now, half_life)
        if not air_quality.seal and held_outdoor >= self.options.outdoor_aqi_threshold:
            air_quality = _dc_replace(air_quality, seal=True, indoor_event=False, purifier_recommended=True,
                                      pressure=max(air_quality.pressure, 0.8),
                                      reason="holding seal through an outdoor air-quality lull")
        target = resolve_effective_target(snapshot, memory, {"solar": solar, "energy": energy, "humidity": humidity, "mold": mold, "air_quality": air_quality}, self.options)
        thermal = evaluate_thermal(snapshot, memory, solar.pressure, energy.penalty, self.thermal.cooling_bias(), target.effective_target, self._anticipation(snapshot))
        return {"safety": evaluate_safety(snapshot, self.capabilities, self.options), "solar": solar, "energy": energy, "thermal": thermal, "humidity": humidity, "mold": mold, "air_quality": air_quality, "target": target}

    async def async_apply_decision(self, decision=None, snapshot=None) -> None:
        if not self.data:
            return
        await self.executor.apply(snapshot if snapshot is not None else self.data["snapshot"], decision if decision is not None else self.data["decision"])

    def reset_learning(self) -> None:
        self.learning.reset()

    def unload(self) -> None:
        remove = getattr(self, "_remove_auto_apply_listener", None)
        if remove:
            remove()

    # --- multi-entity state readers (every slot is a list) ---
    def _states(self, key: str):
        return [s for eid in as_list(self.config.get(key)) if (s := self.hass.states.get(eid)) is not None]

    @staticmethod
    def _usable(states):
        return [s for s in states if s.state not in _UNSET]

    @staticmethod
    def _attr(state, name: str, default=None):
        return state.attributes.get(name, default) if state is not None else default

    def _celsius_attr(self, state, name: str, unit):
        value = self._attr(state, name)
        try:
            return to_celsius(float(value), unit) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _floats(self, key: str, temperature: bool = False):
        out = []
        for s in self._usable(self._states(key)):
            try:
                value = float(s.state)
            except (TypeError, ValueError):
                continue
            out.append(to_celsius(value, self._attr(s, "unit_of_measurement")) if temperature else value)
        return out

    def _mean(self, key: str, temperature: bool = False):
        vals = self._floats(key, temperature)
        return sum(vals) / len(vals) if vals else None

    def _max(self, key: str):
        vals = self._floats(key)
        return max(vals) if vals else None

    def _lightning(self):
        """If a Blitzortung sensor is configured (confirming the integration is
        installed), scan its per-strike geo_location.lightning_strike_* entities and
        compute the dynamic hold. Returns (hold, closest_km, strikes)."""
        if not self.capabilities.lightning:
            return False, None, 0
        now = dt_util.utcnow().timestamp()
        seen, distances, ages = set(), [], []
        for state in self.hass.states.async_all("geo_location"):
            if "lightning" not in state.entity_id and self._attr(state, "source") != "blitzortung":
                continue
            external_id = self._attr(state, "external_id", state.entity_id)
            if external_id in seen:
                continue
            seen.add(external_id)
            try:
                distance = float(state.state)
            except (TypeError, ValueError):
                continue
            if self._attr(state, "unit_of_measurement") in ("mi", "miles"):
                distance *= 1.609344
            published = self._attr(state, "publication_date")
            if isinstance(published, (int, float)):
                timestamp = float(published)
            elif published is not None:
                parsed = dt_util.parse_datetime(str(published))
                timestamp = parsed.timestamp() if parsed else None
            else:
                timestamp = None
            if timestamp is None:
                continue
            distances.append(distance)
            ages.append(now - timestamp)
        return lightning_hold(distances, ages, self.options.lightning_distance)

    def _any_on(self, key: str) -> bool:
        return any(s.state == "on" for s in self._states(key))

    def _occupied(self, key: str) -> bool:
        usable = self._usable(self._states(key))
        if not usable:
            return True  # no presence info -> assume occupied
        return any((s.state == "on") if s.domain == "binary_sensor" else (s.state == "home") for s in usable)

    def _occupied_held(self):
        """Occupancy with a debounce hold: stays occupied for a decaying window after
        the last detection, so a person sitting still doesn't flip the room to away."""
        raw = self._occupied(CONF_OCCUPANCY)
        held = self.presence_memory.update(1.0 if raw else 0.0, dt_util.utcnow().timestamp(), self.options.presence_hold * 60)
        return held >= 0.5

    def _invalid(self, key: str):
        reasons = []
        # The lightning distance sensor is only a "Blitzortung is installed" marker --
        # its value is never used (geo_location strikes provide the data), and it rests
        # at unknown/unavailable whenever there's no recent strike. So flag it only if
        # the entity is genuinely missing, never for a resting state.
        skip_states = key == CONF_LIGHTNING_DISTANCE
        for eid in as_list(self.config.get(key)):
            state = self.hass.states.get(eid)
            if state is None:
                reasons.append(f"{eid} (missing)")
            elif not skip_states and state.state in _UNSET:
                reasons.append(f"{eid} ({state.state})")
        return reasons

    def _forecast_high(self, system_unit):
        """Highest upcoming peak across all configured forecast/weather sources."""
        peaks = []
        for state in self._states(CONF_FORECAST_HIGH):
            entries = self._attr(state, "forecast")
            if isinstance(entries, list) and entries:
                unit = self._attr(state, "temperature_unit") or system_unit
                peak = to_celsius(upcoming_peak(entries, dt_util.utcnow()), unit)
            else:
                try:
                    peak = to_celsius(float(state.state), self._attr(state, "unit_of_measurement") or system_unit)
                except (TypeError, ValueError):
                    peak = None
            if peak is not None:
                peaks.append(peak)
        return max(peaks) if peaks else None

    def _forecast_pressure(self, system_unit):
        """Weighted upcoming-heat pressure (how hot/soon/sustained) across sources."""
        best = 0.0
        for state in self._states(CONF_FORECAST_HIGH):
            entries = self._attr(state, "forecast")
            if isinstance(entries, list) and entries:
                unit = self._attr(state, "temperature_unit") or system_unit
                best = max(best, heat_outlook(entries, dt_util.utcnow(), float(self.options.target), unit))
        return best

    async def async_load_model(self) -> None:
        """Reload what the room taught us last time. Days of learning shouldn't be thrown
        away by a restart -- and it's only ~1 kB, because a recursive fit keeps the lessons,
        never the samples."""
        try:
            stored = await self._model_store.async_load()
        except Exception:  # a corrupt store must never block startup; re-learning is safe
            _LOGGER.debug("Could not load the thermal model; starting fresh")
            return
        if not stored:
            return
        if self.thermal.restore(stored.get("thermal")):
            _LOGGER.debug("Restored thermal model (%s samples)", self.thermal.samples)
        if self.air.restore(stored.get("air")):
            _LOGGER.debug("Restored air model (%s samples)", self.air.samples)

    def _save_model(self) -> None:
        """Debounced write -- the coordinator runs every minute, the disk shouldn't."""
        self._model_store.async_delay_save(lambda: {"thermal": self.thermal.as_dict(), "air": self.air.as_dict()}, 300)

    @staticmethod
    def _solar_proxy(snapshot) -> float:
        """0..1 'how much sun is landing on this room' -- measured lux when there is a
        sensor, otherwise the sun's height in the sky."""
        if snapshot is None:
            return 0.0
        if snapshot.lux is not None:
            return min(max(snapshot.lux, 0.0) / 50000.0, 1.0)
        if snapshot.sun_up and snapshot.sun_elevation is not None:
            return min(max(snapshot.sun_elevation, 0.0) / 60.0, 1.0)
        return 0.0

    def _anticipation(self, snapshot) -> float:
        """How much warmer the room will be shortly if left alone, from the learned model
        (or its context-bucket fallback while the model is still warming up)."""
        return self.thermal.anticipation(
            snapshot.indoor_temp, snapshot.outdoor_temp,
            solar=self._solar_proxy(snapshot), sun_up=bool(snapshot.sun_up),
            occupied=bool(snapshot.occupancy),
        )

    def _price_signals(self):
        """(rank 0..1, precool_ok) from the price sensor's forecast attributes.
        Rank is the current price's percentile within the upcoming day; precool_ok is
        True when now is the cheapest upcoming window. Falls back (no forecast) to
        cheap = at/below the daily average."""
        if self.options.pricing_mode != _PRICING_SPOT:
            return None, True  # fixed price: no time-of-use games, precool freely for comfort
        current = self._mean(CONF_PRICE)
        if current is None:
            return None, False
        # Forecast arrays live on a dedicated sensor for some integrations (Elpriset)
        # and on the price sensor itself for others (Nordpool); try both.
        attributes = {}
        for key in (CONF_PRICE_FORECAST, CONF_PRICE):
            found = False
            for state in self._usable(self._states(key)):
                attributes = state.attributes
                found = True
                break
            if found and (price_series(attributes, dt_util.now()) or day_values(attributes, dt_util.now())):
                break
        now = dt_util.now()
        today = day_values(attributes, now)
        upcoming = price_series(attributes, now)
        if today or upcoming:
            rank = _price_rank(current, today if today else [v for _, v in upcoming])
            # Bank coolth only in the cheapest upcoming window AND when it's genuinely
            # cheap (at/below the day's median) -- not merely the least-bad pricey hour.
            precool = in_cheapest_window(upcoming, now) and (rank is None or rank <= 0.5)
            return rank, precool
        average = self._mean(CONF_PRICE_AVERAGE)
        return None, (average is None or current <= average)

    def _aqi(self):
        """Worst (highest) AQI and its dominant factor across all AQI sensors."""
        best = None
        dominant = None
        for s in self._usable(self._states(CONF_AQI)):
            try:
                value = float(s.state)
            except (TypeError, ValueError):
                continue
            if best is None or value > best:
                best = value
                dominant = self._attr(s, "dominant_factor")
        return best, dominant

    def _snapshot(self) -> Snapshot:
        try:
            system_unit = self.hass.config.units.temperature_unit
        except AttributeError:
            system_unit = "°C"
        indoor = self._mean(CONF_TEMPERATURE, temperature=True)
        climates = self._usable(self._states(CONF_CLIMATE))
        climate_valid = bool(climates)
        if indoor is None and climates:
            temps = [t for s in climates if (t := self._celsius_attr(s, "current_temperature", system_unit)) is not None]
            indoor = sum(temps) / len(temps) if temps else None

        # combined climate capability: only command what EVERY unit supports
        if climates:
            mode_sets = [set(self._attr(s, "hvac_modes", []) or []) for s in climates]
            hvac_modes = sorted(set.intersection(*mode_sets)) if mode_sets else []
            mins = [m for s in climates if (m := self._celsius_attr(s, "min_temp", system_unit)) is not None]
            maxs = [m for s in climates if (m := self._celsius_attr(s, "max_temp", system_unit)) is not None]
            min_temp = max(mins) if mins else None   # highest floor is safe for all
            max_temp = min(maxs) if maxs else None    # lowest ceiling is safe for all
            hvac_mode = next((s.state for s in climates if s.state in _MANAGED), climates[0].state)
        else:
            hvac_modes = []
            min_temp = max_temp = None
            hvac_mode = "off"

        covers = self._usable(self._states(CONF_BLINDS))
        humidifiers = self._usable(self._states(CONF_HUMIDIFIER))
        first_h = humidifiers[0] if humidifiers else None
        weathers = self._usable(self._states(CONF_WEATHER))
        outdoors = [o for s in weathers if (o := self._celsius_attr(s, "temperature", self._attr(s, "temperature_unit") or system_unit)) is not None]
        aqi_value, aqi_dominant = self._aqi()
        lh, lc, ls = self._lightning()
        sun = self.hass.states.get("sun.sun")
        invalid = [reason for key in ENTITY_KEYS for reason in self._invalid(key)]
        return Snapshot(
            indoor_temp=indoor if indoor is not None else 0.0,
            humidity=(humidity := self._mean(CONF_HUMIDITY)),
            feels_like=_feels_like(indoor, humidity, self.options.humidity_cooling),
            outdoor_temp=sum(outdoors) / len(outdoors) if outdoors else None,
            occupancy=self._occupied_held(),
            window_open=self._any_on(CONF_WINDOW),
            portable_ac=self.options.portable_ac,
            # The exhaust hose is vented only via its OWN vent sensor or the manual switch --
            # a generic door/window contact must never imply the hose is vented.
            vented=self._any_on(CONF_VENT) or self.vent_override,
            quiet=self.options.quiet_hours and in_quiet_hours(dt_util.now().time(), self.options.quiet_start, self.options.quiet_end),
            energy_price=self._mean(CONF_PRICE),
            price_average=self._mean(CONF_PRICE_AVERAGE),
            price_rank=(price_signals := self._price_signals())[0],
            price_precool=price_signals[1],
            co2=self._max(CONF_CO2),
            voc=self._max(CONF_VOC),
            lux=self._max(CONF_LUX),
            humidifier_class=self._attr(first_h, "device_class"),
            aqi=aqi_value,
            aqi_dominant_factor=aqi_dominant,
            outdoor_aqi=self._max(CONF_OUTDOOR_AQI),
            pm25=self._max(CONF_PM25),
            pm10=self._max(CONF_PM10),
            dark=(lux := self._max(CONF_LUX)) is not None and self.options.sleep_lux > 0 and lux <= self.options.sleep_lux,
            forecast_high=self._forecast_high(system_unit),
            forecast_pressure=self._forecast_pressure(system_unit),
            hvac_mode=hvac_mode,
            hvac_modes=hvac_modes,
            min_temp=min_temp,
            max_temp=max_temp,
            temperature_unit=system_unit,
            sun_up=sun is not None and sun.state == "above_horizon",
            sun_elevation=self._attr(sun, "elevation"),
            smoke_detected=self._any_on(CONF_SMOKE),
            lightning_hold=lh,
            lightning_closest=lc,
            lightning_strikes=ls,
            lightning_band=lightning_band(lc) if lh else "clear",
            outlet_overloaded=self._any_on(CONF_OUTLET_OVERLOAD),
            temperature_valid=indoor is not None,
            climate_valid=climate_valid,
            cover_closed=bool(covers) and all(s.state == "closed" for s in covers),
            invalid_entities=invalid,
        )

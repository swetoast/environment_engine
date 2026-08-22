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
    """Everything needed to reason about a decision from a bug report alone.

    The learned models are the important part: without them a report shows *what* the
    engine did but never *why* it thought that was right, and the fits are the one piece
    of state that cannot be reconstructed from the config and the current readings.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    data = coordinator.data or {}
    thermal, air = coordinator.thermal, coordinator.air
    return {
        "entry_data": dict(entry.data),
        "entry_options": dict(entry.options),
        "resolved_options": _dump(coordinator.options),
        "decision": _dump(data.get("decision")),
        "raw_decision": _dump(data.get("raw_decision")),
        "snapshot": _dump(data.get("snapshot")),
        "evaluations": {name: _dump(result) for name, result in data.get("evaluations", {}).items()},
        "capabilities": _dump(data.get("capabilities")),
        "runtime": data.get("runtime"),
        "runtime_today": data.get("runtime_today"),
        "learning": {
            "drying": _dump(data.get("learning")),
            "thermal_model": {
                "samples": thermal.samples,
                "rejected": thermal.rejected,
                "confidence": round(thermal.confidence, 3),
                "leakiness_per_min": round(thermal.leakiness, 5),
                "solar_gain": round(thermal.solar_gain, 5),
                "cooling_power_per_min": round(thermal.cooling_power, 5),
                "occupied_gain_per_min": round(thermal.occupied_gain, 5),
                "internal_gain_per_min": round(thermal.internal_gain, 5),
                "time_constant_min": thermal.time_constant,
                "effectiveness": round(thermal.effectiveness, 3),
                "cooling_bias": round(thermal.cooling_bias(), 4),
                "struggling": thermal.struggling,
                "unexplained_drift_per_min": round(thermal.unexplained_drift, 5),
                "anomaly_score": round(thermal.anomaly_score, 2),
                "bucket_rates": dict(thermal.buckets.rates),
                "cooling_effect_by_band": dict(thermal.cooling_effect),
            },
            "air_model": {
                "samples": air.samples,
                "rejected": air.rejected,
                "confidence": round(air.confidence, 3),
                "clean_rate_per_min": round(air.clean_rate, 5),
                "deposition_per_min": round(air.deposition, 5),
                "infiltration": round(air.infiltration, 5),
                "generation": round(air.generation, 4),
                "peak_clean_rate": round(air.peak_cadr, 5),
                "filter_health": air.filter_health,
            },
        },
    }

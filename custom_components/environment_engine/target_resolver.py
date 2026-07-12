"""Effective climate target resolver.

One comfort baseline; the engine derives comfort/eco/sleep and pre-cooling itself
by moving the setpoint within safe bounds from live conditions:

  reactive drop   -> hot room now / warming trend       (cool harder)
  outdoor drop    -> hot outside                          (preemptive, small)
  precool drop    -> hot period forecast AND power cheap  (bank coolth early)
  night relax     -> sun down                             (quieter, sleep-like)
  energy relax    -> expensive power now                  (eco)
  ventilation     -> open window, cooler outside          (let it work)

'Away' is handled by the planner idling an empty room. Solar stays a thermal-
confidence bonus (whether to run) and energy stays both a confidence penalty and
the relax term here (how hard), each capped so they don't compound past bounds.
"""
from __future__ import annotations
from dataclasses import dataclass
from .psychrometrics import dew_point

_MAX_DROP = 3.0          # reactive (indoor heat + trend)
_SOFTNESS = 3.0
_TREND_DROP = 0.5
_OUTDOOR_HOT = 25.0      # outdoor above this begins a small preemptive drop
_OUTDOOR_SPAN = 10.0
_MAX_OUTDOOR_DROP = 1.0
_MAX_PRECOOL = 1.5
_MAX_RELAX = 3.0
_NIGHT_RELAX = 1.0
_SLEEP_RELAX = 1.5
_VENT_RELAX = 1.0
_ENERGY_RELAX = 1.5
_MAX_CORRECTION = 4.0


@dataclass(slots=True)
class TargetResult:
    base_target: int
    effective_target: int
    reason: str
    cooling_drop: float = 0.0      # how much the setpoint was pushed down (surfaced)
    relaxation: float = 0.0        # how much it was eased up for eco/sleep (surfaced)
    precool: float = 0.0
    limited_by_min: bool = False
    limited_by_max: bool = False


def _clamp(value, low, high):
    return max(low, min(high, value))


def resolve_effective_target(snapshot, memory, evaluations, options) -> TargetResult:
    base = float(options.target)
    energy = evaluations.get("energy")

    # --- reactive drop (indoor heat excess + warming trend), anchored to baseline ---
    excess = max(0.0, snapshot.indoor_temp - base)
    thermal_drop = (excess * _MAX_DROP / (excess + _SOFTNESS)) if excess > 0 else 0.0
    trend_drop = min(max(memory.temperature_trend, 0.0), 1.0) * _TREND_DROP if memory.temperature_trend > 0.15 else 0.0
    reactive_drop = min(thermal_drop + trend_drop, _MAX_DROP)

    # --- preemptive outdoor-heat drop (small; solar already biases confidence) ---
    outdoor_drop = 0.0
    if snapshot.outdoor_temp is not None:
        outdoor_drop = _clamp((snapshot.outdoor_temp - _OUTDOOR_HOT) / _OUTDOOR_SPAN, 0.0, 1.0) * _MAX_OUTDOOR_DROP

    # --- forecast pre-cooling: bank coolth ahead of a heat load, but only during the
    # cheapest upcoming price window (load-shifting). price_precool encodes that window
    # (or, without a price forecast, simply "at/below the daily average"). ---
    precool_drop = 0.0
    if snapshot.forecast_pressure > 0 and snapshot.price_precool:
        precool_drop = _clamp(snapshot.forecast_pressure, 0.0, 1.0) * _MAX_PRECOOL

    # Muggy comfort is now handled upstream by the feels-like temperature (a humid
    # room reads warmer to the thermal evaluator), so there is no separate target drop.
    total_drop = reactive_drop + outdoor_drop + precool_drop

    # --- relaxations (automatic eco / sleep / ventilation) ---
    relax = 0.0
    factors = []
    air_quality = evaluations.get("air_quality")
    sealed = air_quality is not None and air_quality.seal
    if not snapshot.sun_up:
        if snapshot.dark:
            relax += _SLEEP_RELAX
            factors.append("sleep")
        else:
            relax += _NIGHT_RELAX
            factors.append("night")
    if energy is not None and energy.expensive:
        relax += min(energy.penalty / 0.3, 1.0) * _ENERGY_RELAX
        factors.append("energy price")
    # Passive ventilation eases the setpoint -- but not during an outdoor
    # air-quality event, when we keep the room sealed and cooling actively.
    if not sealed and snapshot.window_open and snapshot.outdoor_temp is not None and snapshot.outdoor_temp < snapshot.indoor_temp:
        relax += _VENT_RELAX
        factors.append("ventilation")
    relaxation = min(relax, _MAX_RELAX)

    raw = _clamp(base - total_drop + relaxation, base - _MAX_CORRECTION, base + _MAX_CORRECTION)

    # Condensation guard: never target below the room's dew point + margin, or the
    # AC would drive surfaces toward condensation. A humid (high dew point) room is
    # thus bounded here and left to dry/dehumidify, which lowers the dew point and
    # unlocks deeper cooling next cycle.
    dew = dew_point(snapshot.indoor_temp, snapshot.humidity)
    dew_floor = None
    pre_dew = raw
    if dew is not None and options.dewpoint_margin > 0:
        dew_floor = dew + options.dewpoint_margin
        raw = max(raw, dew_floor)

    low = snapshot.min_temp if snapshot.min_temp is not None else 16.0
    high = snapshot.max_temp if snapshot.max_temp is not None else 30.0
    clamped = _clamp(raw, low, high)
    effective = int(round(clamped))
    dew_limited = dew_floor is not None and raw > pre_dew + 0.01

    if effective < int(round(base)):
        if precool_drop > 0 and precool_drop >= max(reactive_drop, outdoor_drop):
            reason = "pre-cooling ahead of forecast heat while power is cheap"
        else:
            reason = "lowered setpoint for heat load"
    elif effective > int(round(base)):
        reason = "relaxed setpoint for " + ", ".join(factors) if factors else "relaxed setpoint"
    else:
        reason = "holding baseline setpoint"
    if dew_limited:
        reason += " (held above dew point to avoid condensation)"

    return TargetResult(
        base_target=int(round(base)),
        effective_target=effective,
        reason=reason,
        cooling_drop=round(total_drop, 2),
        relaxation=round(relaxation, 2),
        precool=round(precool_drop, 2),
        limited_by_min=clamped <= low,
        limited_by_max=clamped >= high,
    )

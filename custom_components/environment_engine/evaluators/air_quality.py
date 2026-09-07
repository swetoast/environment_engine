from __future__ import annotations
from dataclasses import dataclass
from ..confidence import clamp
@dataclass(slots=True)
class AirQualityResult:
    pressure: float
    purifier_recommended: bool
    reason: str
    dominant: str | None = None
    seal: bool = False
    indoor_event: bool = False
    seal_threat: str | None = None   # "particulate" (purifier helps) or "gas" (it doesn't)


def evaluate_air_quality(snapshot, options) -> AirQualityResult:
    """Air-quality pressure with particle size- and source-awareness.

    Size: fine particles (PM1/PM2.5 -- combustion, smoke, cooking) pass filters and
    lungs and warrant hard purification; coarse (PM10 -- dust, pollen) is weighted
    lower, so the *same* excess drives a gentler response.

    Source: a high *indoor* particle level with clean *outdoor* air is an indoor
    event (cooking, candle) -> purify hard AND air out (opening up helps). High
    outdoor air is an infiltration event -> seal and purify, don't ventilate. This
    indoor-vs-outdoor distinction is exactly what a single AQI number can't make.
    """
    # Outdoor threats, split by whether a purifier can actually do anything about them.
    # Sealing keeps everything out, but a HEPA filter only catches PARTICULATES (PM, pollen)
    # -- gases (ozone, CO, NO2, SO2) pass straight through it. So the engine seals for
    # either, but only claims the purifier as a fix for the filterable kind.
    aqi_high = snapshot.outdoor_aqi is not None and snapshot.outdoor_aqi >= options.outdoor_aqi_threshold
    pollen_high = snapshot.outdoor_pollen is not None and snapshot.outdoor_pollen >= options.pollen_threshold
    gas_high = snapshot.outdoor_gas is not None and snapshot.outdoor_gas >= 0.5
    filterable_outdoor = aqi_high or pollen_high      # PM/pollen: seal AND purify
    gaseous_outdoor = gas_high                        # gas: seal only
    outdoor_high = filterable_outdoor or gaseous_outdoor

    # --- indoor particle analysis ---
    fine = snapshot.pm25
    coarse = snapshot.pm10
    fine_ratio = fine / options.pm25_threshold if fine is not None else 0.0
    coarse_ratio = coarse / options.pm10_threshold if coarse is not None else 0.0
    pm_pressure = clamp(max(fine_ratio, coarse_ratio * 0.6))  # coarse weighted lower
    pm_high = fine_ratio >= 1.0 or coarse_ratio >= 1.0
    pm_dominant = None
    if max(fine_ratio, coarse_ratio) >= 0.5:   # only name a driver once it actually matters
        pm_dominant = "PM2.5" if fine_ratio >= coarse_ratio else "PM10"

    # --- base indoor pressure: aggregate AQI sensor, else raw CO2/VOC ---
    if snapshot.aqi is not None:
        threshold = float(options.aqi_threshold)
        pressure = clamp((snapshot.aqi - threshold) / 100.0)
        recommended = snapshot.aqi >= threshold + 10  # small deadband so it doesn't flap at the boundary
        dominant = snapshot.aqi_dominant_factor
        if recommended:
            reason = f"air quality elevated (AQI {int(snapshot.aqi)}" + (f", {dominant}-driven)" if dominant else ")")
        else:
            reason = f"air quality is good (AQI {int(snapshot.aqi)})"
    else:
        co2 = 0.0 if snapshot.co2 is None else clamp((snapshot.co2 - options.co2_threshold) / 1600.0)
        voc = 0.0 if snapshot.voc is None else clamp((snapshot.voc - options.voc_threshold) / max(options.voc_threshold, 1.0))
        pressure = max(voc, co2)
        dominant = None if pressure == 0 else ("VOC" if voc >= co2 else "CO2")
        recommended = pressure >= 0.5
        reason = "air quality pressure is elevated" if recommended else "air quality pressure is low"

    # Fold the size-weighted particle pressure into the indoor picture. Particles are the
    # one thing a purifier is actually built to remove, so once fine/coarse pressure is the
    # loudest signal it drives both the recommendation and the dominant label -- not only at
    # the hard pm_high cliff. Recommending purification tracks the SAME pressure the sensor
    # reports, so the two can't disagree (a 0.60 particle load no longer reads "don't run
    # it"). The 0.5 gate matches the CO2/VOC path.
    if pm_pressure > pressure:
        pressure = pm_pressure
        dominant = pm_dominant or dominant
    if pm_high or pm_pressure >= 0.5:
        recommended = True
        dominant = pm_dominant or dominant

    seal = outdoor_high
    seal_threat = "particulate" if filterable_outdoor else ("gas" if gaseous_outdoor else None)
    # An indoor particle event worth airing out: enough fine/coarse load to warrant
    # purifying, and clean outdoor air to flush it with. Uses the same 0.5 gate as the
    # recommendation so "purify" and "air out" agree, rather than waiting for the ratio to
    # top 1.0 -- a real cooking event at 80% should open up, not sit sealed.
    indoor_particles = pm_high or pm_pressure >= 0.5
    indoor_event = indoor_particles and not outdoor_high

    if seal and filterable_outdoor:
        # Particulate outside -- pollen or PM. Seal and run the purifier hard; the filter
        # genuinely removes what leaks in.
        pressure = max(pressure, 0.8)
        recommended = True
        if pollen_high and not aqi_high:
            reason = f"outdoor pollen event ({snapshot.outdoor_pollen:.1f} grains/m³) — sealing and purifying"
        else:
            reason = f"outdoor air-quality event (outdoor AQI {int(snapshot.outdoor_aqi)}) — sealing and purifying"
    elif seal and gaseous_outdoor:
        # Gas outside -- ozone, CO, NO2. Seal to stop it getting in, but do NOT claim the
        # purifier fixes it: a HEPA filter can't scrub a gas. Raise pressure modestly so the
        # engine prefers keeping the room shut, without pretending to clean the air.
        pressure = max(pressure, 0.4)
        reason = "outdoor gas event — sealing (a filter cannot remove gases; keeping it out)"
    elif indoor_event:
        recommended = True  # pressure already reflects the (size-weighted) particle level
        reason = f"indoor particle event ({pm_dominant}) — purifying and airing out"

    return AirQualityResult(pressure, recommended, reason, dominant, seal, indoor_event, seal_threat)

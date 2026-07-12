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
    outdoor_high = snapshot.outdoor_aqi is not None and snapshot.outdoor_aqi >= options.outdoor_aqi_threshold

    # --- indoor particle analysis ---
    fine = snapshot.pm25
    coarse = snapshot.pm10
    fine_ratio = fine / options.pm25_threshold if fine is not None else 0.0
    coarse_ratio = coarse / options.pm10_threshold if coarse is not None else 0.0
    pm_pressure = clamp(max(fine_ratio, coarse_ratio * 0.6))  # coarse weighted lower
    pm_high = fine_ratio >= 1.0 or coarse_ratio >= 1.0
    pm_dominant = None
    if fine_ratio > 0 or coarse_ratio > 0:
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

    # fold size-weighted particle pressure into the indoor picture
    pressure = max(pressure, pm_pressure)
    if pm_high:
        recommended = True
        dominant = pm_dominant or dominant

    seal = outdoor_high
    indoor_event = pm_high and not outdoor_high

    if seal:
        pressure = max(pressure, 0.8)
        recommended = True
        reason = f"outdoor air-quality event (outdoor AQI {int(snapshot.outdoor_aqi)}) — sealing and purifying"
    elif indoor_event:
        recommended = True  # pressure already reflects the (size-weighted) particle level
        reason = f"indoor particle event ({pm_dominant}) — purifying and airing out"

    return AirQualityResult(pressure, recommended, reason, dominant, seal, indoor_event)

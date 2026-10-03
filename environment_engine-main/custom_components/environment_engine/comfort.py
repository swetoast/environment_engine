"""Thermal comfort and humidity context (pure, no dependencies).

Two things live here, and neither of them controls the temperature:

  * Fanger's PMV / PPD (ISO 7730 / ASHRAE 55), an independent implementation. It is
    shown on the Cooling Demand sensor so you can see how the air reads on the comfort
    scale. It never picks a setpoint.
  * The humidity rules: how many whole degrees damp air takes OFF the setpoint, and when
    DRY mode is worth running.

The user's setpoint is the controller. Context here can only make the engine cool harder.
"""
from __future__ import annotations
import math
from .psychrometrics import dew_point


MET_SEATED = 1.1

CLO_SUMMER = 0.5        # light trousers, short sleeves


def _clamp(value, low, high):
    return max(low, min(value, high))


def vapour_pressure(temp_c: float, relative_humidity: float) -> float:
    """Partial water-vapour pressure in Pa, as ISO 7730 uses it."""
    rh = _clamp(relative_humidity, 0.0, 100.0)
    return rh * 10.0 * math.exp(16.6536 - 4030.183 / (temp_c + 235.0))


def pmv(temp_c: float, relative_humidity: float, air_speed: float = 0.1,
        met: float = MET_SEATED, clo: float = CLO_SUMMER,
        radiant_c: float | None = None, work: float = 0.0) -> float | None:
    """Predicted Mean Vote (-3..+3). `radiant_c` defaults to air temperature, which is
    right for a room without strong radiant asymmetry (no sun on you, no cold window).
    Returns None if an input is missing."""
    if temp_c is None or relative_humidity is None:
        return None
    radiant = temp_c if radiant_c is None else radiant_c
    vel = max(0.0, air_speed)
    icl = 0.155 * clo                       # clothing insulation, m2K/W
    m = met * 58.15                         # metabolic rate, W/m2
    w = work * 58.15
    mw = m - w
    pa = vapour_pressure(temp_c, relative_humidity)

    # Clothing area factor.
    fcl = 1.00 + 1.290 * icl if icl <= 0.078 else 1.05 + 0.645 * icl
    hcf = 12.1 * math.sqrt(vel)             # forced convection
    taa = temp_c + 273.0
    tra = radiant + 273.0

    # Solve the clothing surface temperature iteratively.
    tcla = taa + (35.5 - temp_c) / (3.5 * icl + 0.1)
    p1 = icl * fcl
    p2 = p1 * 3.96
    p3 = p1 * 100.0
    p4 = p1 * taa
    p5 = 308.7 - 0.028 * mw + p2 * (tra / 100.0) ** 4
    xn = tcla / 100.0
    xf = xn
    hc = hcf
    for _ in range(150):
        xf = (xf + xn) / 2.0
        hcn = 2.38 * abs(100.0 * xf - taa) ** 0.25   # natural convection
        hc = max(hcf, hcn)
        xn = (p5 + p4 * hc - p2 * xf ** 4) / (100.0 + p3 * hc)
        if abs(xn - xf) <= 0.00015:
            break
    tcl = 100.0 * xn - 273.0

    # Heat-loss terms (W/m2).
    hl1 = 3.05 * 0.001 * (5733.0 - 6.99 * mw - pa)          # skin diffusion
    hl2 = 0.42 * (mw - 58.15) if mw > 58.15 else 0.0        # sweating
    hl3 = 1.7 * 0.00001 * m * (5867.0 - pa)                 # latent respiration
    hl4 = 0.0014 * m * (34.0 - temp_c)                      # dry respiration
    hl5 = 3.96 * fcl * (xn ** 4 - (tra / 100.0) ** 4)       # radiation
    hl6 = fcl * hc * (tcl - temp_c)                         # convection

    sensitivity = 0.303 * math.exp(-0.036 * m) + 0.028
    return _clamp(sensitivity * (mw - hl1 - hl2 - hl3 - hl4 - hl5 - hl6), -4.0, 4.0)


def ppd(pmv_value: float | None) -> float | None:
    """Predicted Percentage Dissatisfied. Bottoms out near 5% -- even at perfect
    neutrality some people are unhappy, which is exactly why an individual's comfort
    can't be read off PMV alone."""
    if pmv_value is None:
        return None
    return 100.0 - 95.0 * math.exp(-0.03353 * pmv_value ** 4 - 0.2179 * pmv_value ** 2)


def sensation(pmv_value: float | None) -> str:
    """Plain-language reading of a PMV value, for the user-facing sensor."""
    if pmv_value is None:
        return "unknown"
    if pmv_value <= -2.5:
        return "cold"
    if pmv_value <= -1.5:
        return "cool"
    if pmv_value <= -0.5:
        return "slightly cool"
    if pmv_value < 0.5:
        return "comfortable"
    if pmv_value < 1.5:
        return "slightly warm"
    if pmv_value < 2.5:
        return "warm"
    return "hot"


# ---------------------------------------------------------------------------
# Context for the controller.
#
# Temperature is the controller. These functions never choose a temperature and
# never stand the compressor down -- they only report how wet the air is, and by
# how many whole degrees that should make the engine cool HARDER. Context can
# subtract from the setpoint. It can never add.
#
# The AC takes whole degrees, so penalties are whole degrees. A condition that
# doesn't warrant a full degree warrants nothing.
# ---------------------------------------------------------------------------

COIL_TEMP_C = 12.0        # evaporator surface; below this dew point nothing condenses
# Dew point, because that is what people feel as sticky and, unlike RH, it does not move
# when the temperature does.
#   <=11 C  dry, nobody notices      15-17 C  noticeable, sensitive people react
#   11-15   comfortable              17-20 C  sticky for most      >20 C  oppressive
DEW_LIMITS = {"tolerant": 17.0, "normal": 15.0, "sensitive": 13.0, "very_sensitive": 11.0}
DEFAULT_DEW_LIMIT = 15.0
_DEW_DEADBAND = 1.5       # how far dew must fall back before DRY releases


def dew_limit_for(sensitivity) -> float:
    """The dew point above which the air counts as too wet for this person."""
    return DEW_LIMITS.get(sensitivity, DEFAULT_DEW_LIMIT)


def humidity_penalty(temp_c, relative_humidity, sensitivity="normal") -> int:
    """Whole degrees to take OFF the setpoint because the air is damp.

    Muggy air makes the same temperature feel worse, so the answer is to cool harder,
    not to sit at a higher number. Returns 0, 1 or 2 -- never negative, so it can only
    ever make the room colder.
    """
    dew = dew_point(temp_c, relative_humidity)
    if dew is None:
        return 0
    limit = dew_limit_for(sensitivity)
    if dew <= limit:
        return 0
    return 2 if dew >= limit + 3.0 else 1


def should_dehumidify(snapshot, options, at_or_below_target: bool) -> bool:
    """Whether DRY is the right mode right now.

    DRY only makes sense when the temperature is already fine and the air is still too
    wet. If the room is warm, COOL runs instead -- a coil below the dew point chills and
    dehumidifies at the same time, so cooling handles both.

    Allowed during quiet hours: DRY is the compressor at low load, not a cooling blast.
    The one hard block is an unvented portable unit, which would dump its condenser heat
    back into the room.
    """
    if not at_or_below_target or snapshot.humidity is None:
        return False
    if options.portable_ac and not snapshot.vented:
        return False
    dew = dew_point(snapshot.indoor_temp, snapshot.humidity)
    if dew is None or dew <= COIL_TEMP_C:
        return False          # nothing for the coil to condense
    return dew > dew_limit_for(options.humidity_sensitivity)


def dehumidify_satisfied(snapshot, options) -> bool:
    """Release DRY once the air has dried past the limit, with a deadband so it doesn't
    chatter around the threshold."""
    dew = dew_point(snapshot.indoor_temp, snapshot.humidity)
    if dew is None:
        return True
    return dew < dew_limit_for(options.humidity_sensitivity) - _DEW_DEADBAND

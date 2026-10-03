"""Dynamic lightning hold from Blitzortung geo_location strikes (safety-critical).

The model is the Roborock Helper lightning model, adapted for an air conditioner: an AC is a
much larger electrical load than a vacuum and a far more attractive path for a surge, so it
reacts further out, holds longer, and -- unlike the vacuum -- has NO "advisory" tier. Every
strike within the reaction radius is a hard stop; only the timeout length varies with distance
and storm intensity.

    hold active while:
        age_of_closest_strike <= T_BASE + (T_MAX - T_BASE) * max( (1 - d/D_MAX)**ALPHA , min(1, N/N_MAX) )
        AND closest strike <= D_MAX

  d = distance of the closest strike (km)   N = active strike count
  Closer and busier storms hold longer; the hold auto-releases as the storm ages out.

Config gates this: the user points at a Blitzortung sensor in the Global setup to confirm the
integration is installed; only then does the coordinator scan the per-strike
``geo_location.lightning_strike_*`` entities and feed their distances and ages here.
"""
from __future__ import annotations

# Tuning. Times in seconds, distances in km. AC-adapted from the Roborock vacuum values
# (D_MAX 30->40, T_BASE 15->20 min, T_MAX 45->60 min): a bigger target, so wider and longer.
T_BASE = 1200.0     # 20 min: minimum hold for any strike within D_MAX (at the 40 km edge)
T_MAX = 3600.0      # 60 min: HARD CAP, for a close and intense storm overhead
D_MAX = 40.0        # reaction radius; beyond this there is no hold
N_MAX = 10.0        # strike count considered maximum intensity
ALPHA = 1.5         # distance-decay exponent

# Proximity bands (km). For the AC these are informational only -- EVERY band within D_MAX
# blocks. They label how close the storm is; they do not change whether it holds.
CLOSE_KM = 10.0     # overhead-ish
NEAR_KM = 20.0      # close


def hold_window_s(distance_km: float, strikes: int) -> float:
    """The dynamic timeout for the closest strike at ``distance_km`` in a storm of ``strikes``.

    Proximity and intensity are combined with max(): whichever is scarier drives the hold. So a
    single nearby strike holds long on its own (a 5 km flash ~= 53 min) rather than needing a
    busy storm to earn it, and a busy distant storm also holds long. This is the deliberate AC
    adaptation of the Roborock model, where the two were multiplied (a lone strike stayed at the
    floor). An AC is a big surge target -- a close strike is dangerous whether or not it's busy.
    """
    d = min(max(distance_km, 0.0), D_MAX)
    proximity = (1.0 - d / D_MAX) ** ALPHA
    intensity = min(1.0, strikes / N_MAX)
    return T_BASE + (T_MAX - T_BASE) * max(proximity, intensity)


def lightning_band(distance_km) -> str:
    """Proximity label for the closest active strike (informational; all bands within D_MAX block)."""
    if distance_km is None or distance_km > D_MAX:
        return "clear"
    if distance_km <= CLOSE_KM:
        return "close"
    if distance_km <= NEAR_KM:
        return "near"
    return "distant"


def lightning_hold(distances_km, ages_s, max_react_km=D_MAX):
    """Return (hold, closest_km, strikes).

    A hold is active when the closest strike is within the reaction radius and its age is
    within the dynamic timeout window. A strike inside the radius that we cannot age fails
    SAFE -- it holds on the base window rather than slip through.
    """
    distances_km = [d for d in (distances_km or []) if d is not None]
    if not distances_km:
        return False, None, 0
    strikes = len(distances_km)
    closest = min(distances_km)

    react = min(max_react_km, D_MAX)
    if closest > react:
        return False, closest, strikes

    ages = ages_s or []
    closest_age = None
    for d, a in zip(distances_km, ages):
        if d == closest and a is not None and a >= 0:
            closest_age = a if closest_age is None else min(closest_age, a)
    if closest_age is None:
        # In range but un-ageable -> fail safe, hold on the base window.
        return True, closest, strikes

    return closest_age <= hold_window_s(closest, strikes), closest, strikes

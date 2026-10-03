from __future__ import annotations
from dataclasses import dataclass
from ..confidence import clamp
from ..const import PRICING_SPOT
@dataclass(slots=True)
class EnergyResult:
    penalty: float
    expensive: bool
    reason: str
_LIMIT = 0.3


def evaluate_energy(snapshot, options) -> EnergyResult:
    """Penalize active cooling when power is expensive.

    Relative mode (preferred): when a reference/daily-average price is available,
    "expensive" means *above today's average*, so it self-tunes across seasons and
    price regimes. Falls back to a fixed SEK threshold when no average is set.
    """
    if options.pricing_mode != PRICING_SPOT:
        return EnergyResult(0.0, False, "fixed-price contract — comfort-first, price ignored")
    if snapshot.energy_price is None:
        return EnergyResult(0.0, False, "energy price unavailable")
    price = snapshot.energy_price
    # Preferred: rank the current price within today's forecast distribution, so
    # "expensive" is a smooth percentile rather than a binary above/below average.
    if snapshot.price_rank is not None:
        rank = snapshot.price_rank
        penalty = clamp((rank - 0.5) / 0.5 * _LIMIT, 0.0, _LIMIT)  # 0 at/below median, full at the top
        pct = round(rank * 100)
        if rank >= 0.75:
            reason = f"price is in the priciest part of today ({pct}th percentile)"
        elif rank <= 0.25:
            reason = f"price is in the cheapest part of today ({pct}th percentile)"
        else:
            reason = f"price is mid-range today ({pct}th percentile)"
        return EnergyResult(penalty, rank >= 0.75, reason)
    average = snapshot.price_average
    if average is not None and average > 0:
        ratio = price / average
        penalty = clamp((ratio - 1.0) * 0.4, 0.0, _LIMIT)
        expensive = ratio >= 1.25
        if expensive:
            reason = f"price is {round((ratio - 1.0) * 100)}% above today's average"
        elif ratio <= 0.9:
            reason = "price is below today's average"
        else:
            reason = "price is near today's average"
        return EnergyResult(penalty, expensive, reason)
    penalty = clamp((price / options.price_high) * 0.3, 0.0, _LIMIT)
    return EnergyResult(penalty, penalty >= 0.25, "energy price is limiting active cooling" if penalty >= 0.25 else "energy price has low impact")

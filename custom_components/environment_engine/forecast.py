"""Parse an upcoming temperature peak from a weather/forecast entity.

Home Assistant weather entities and forecast sensors expose a `forecast`
attribute: a list of hourly entries like {datetime, temperature, ...}. The engine
reads the highest temperature within a short horizon so it can pre-cool ahead of
the heat. Pure and unit-agnostic; the caller converts to Celsius.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from .units import to_celsius

HORIZON_HOURS = 8


def _parse_dt(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def upcoming_peak(forecast, now: datetime, horizon_hours: int = HORIZON_HOURS):
    """Max forecast temperature within `horizon_hours` of `now` (entity's own unit).

    Entries without a parseable time are ignored when any timed entry exists; if
    none are timed, the first few entries are used as a best effort.
    """
    if not isinstance(forecast, list) or not forecast:
        return None
    cutoff = now + timedelta(hours=horizon_hours)
    peak = None
    timed_seen = False
    for entry in forecast:
        if not isinstance(entry, dict):
            continue
        temp = entry.get("temperature")
        if temp is None:
            continue
        try:
            temp = float(temp)
        except (TypeError, ValueError):
            continue
        when = _parse_dt(entry.get("datetime"))
        if when is not None:
            timed_seen = True
            if now <= when <= cutoff:
                peak = temp if peak is None else max(peak, temp)
    if peak is None and not timed_seen:
        # no timestamps at all -> best effort over the first few entries
        temps = []
        for entry in forecast[:horizon_hours]:
            if isinstance(entry, dict) and entry.get("temperature") is not None:
                try:
                    temps.append(float(entry["temperature"]))
                except (TypeError, ValueError):
                    pass
        peak = max(temps) if temps else None
    return peak


def heat_outlook(forecast, now: datetime, comfort_c: float, unit, span_c: float = 6.0, horizon_hours: int = HORIZON_HOURS) -> float:
    """Proximity-weighted upcoming heat above comfort, 0..1.

    Unlike a single peak, this weights how hot, how soon, and how sustained the
    heat is: a sustained hot block this afternoon scores high, a lone spike far
    out scores low. `span_c` above comfort (weighted) saturates to 1.
    """
    if not isinstance(forecast, list) or not forecast:
        return 0.0
    cutoff = now + timedelta(hours=horizon_hours)
    total = 0.0
    weight = 0.0
    for entry in forecast:
        if not isinstance(entry, dict):
            continue
        temp = entry.get("temperature")
        try:
            temp_c = to_celsius(float(temp), unit)
        except (TypeError, ValueError):
            continue
        when = _parse_dt(entry.get("datetime"))
        if when is None or not (now <= when <= cutoff):
            continue
        hours_away = (when - now).total_seconds() / 3600.0
        proximity = max(0.0, 1.0 - hours_away / horizon_hours)  # sooner -> heavier
        excess = max(0.0, temp_c - comfort_c)
        total += min(excess / span_c, 1.0) * proximity
        weight += proximity
    return total / weight if weight else 0.0


def precool_opportunity(forecast, price_series, now: datetime, comfort_c: float, unit,
                        horizon_hours: int = HORIZON_HOURS) -> float:
    """0..1 -- how strongly it's worth banking cooling *right now* against later heat.

    This is the genuine forecast-coupled signal, distinct from "is now a cheap window":
    it fires only when heat is actually coming *later* in the horizon (so cooling now has
    something to pre-empt) AND now is cheaper than that hot stretch will be (so shifting
    the load actually saves). No forecast, no heat-later, or now-not-cheaper -> 0.

    `price_series` is a list of (datetime, price) over the horizon; None disables the
    price test (the opportunity then rests on the heat curve alone, for flat-rate users).
    """
    if not isinstance(forecast, list) or not forecast:
        return 0.0
    cutoff = now + timedelta(hours=horizon_hours)
    # Split the horizon: heat that lands more than ~2h out is "later" and pre-emptable.
    soon = now + timedelta(hours=2)
    later_heat = 0.0
    later_hours = []
    for entry in forecast:
        if not isinstance(entry, dict):
            continue
        try:
            temp_c = to_celsius(float(entry.get("temperature")), unit)
        except (TypeError, ValueError):
            continue
        when = _parse_dt(entry.get("datetime"))
        if when is None or not (soon <= when <= cutoff):
            continue
        excess = max(0.0, temp_c - comfort_c)
        if excess > 0:
            later_heat = max(later_heat, excess)
            later_hours.append(when)
    if later_heat <= 0.0 or not later_hours:
        return 0.0                      # no heat coming later -> nothing to pre-empt

    heat_score = min(later_heat / 6.0, 1.0)   # 6 C over comfort saturates

    if price_series is None:
        return heat_score               # flat-rate: bank on the heat curve alone

    # Price test: is now genuinely cheaper than the hot stretch will be?
    now_price = None
    hot_prices = []
    for when, price in price_series:
        if price is None:
            continue
        if when <= soon:
            now_price = price if now_price is None else min(now_price, price)
        if any(abs((when - h).total_seconds()) < 1800 for h in later_hours):
            hot_prices.append(price)
    if now_price is None or not hot_prices:
        return heat_score * 0.5         # can't compare -> weak signal on heat alone
    hot_price = sum(hot_prices) / len(hot_prices)
    if now_price >= hot_price:
        return 0.0                      # now is not cheaper -> shifting saves nothing
    saving = min((hot_price - now_price) / max(hot_price, 0.01), 1.0)
    return heat_score * (0.5 + 0.5 * saving)   # heat matters, saving sharpens it

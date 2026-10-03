"""Parse upcoming temperature data from weather and forecast entities.

Home Assistant uses timezone-aware datetimes internally, but forecast providers may
return ISO timestamps without an offset. All values are normalized before comparison
so naive and aware timestamps can safely coexist.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo

from .units import to_celsius

HORIZON_HOURS = 8


def _comparison_timezone(now: datetime) -> tzinfo:
    """Return the timezone used for comparisons, defaulting naive values to UTC."""
    return now.tzinfo or timezone.utc


def _normalize_datetime(value: datetime, default_tz: tzinfo) -> datetime:
    """Return an aware datetime expressed in ``default_tz``.

    A timestamp without an offset has no safe timezone information of its own. It is
    interpreted in the same timezone as the comparison clock. Timestamps that already
    carry an offset are converted to that timezone.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=default_tz)
    return value.astimezone(default_tz)


def _parse_dt(value, default_tz: tzinfo = timezone.utc):
    if isinstance(value, datetime):
        return _normalize_datetime(value, default_tz)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return _normalize_datetime(parsed, default_tz)
    return None


def upcoming_peak(forecast, now: datetime, horizon_hours: int = HORIZON_HOURS):
    """Max forecast temperature within ``horizon_hours`` of ``now``.

    Entries without a parseable time are ignored when any timed entry exists. If no
    entries have timestamps, the first entries are used as a best effort.
    """
    if not isinstance(forecast, list) or not forecast:
        return None

    comparison_tz = _comparison_timezone(now)
    now = _normalize_datetime(now, comparison_tz)
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

        when = _parse_dt(entry.get("datetime"), comparison_tz)
        if when is not None:
            timed_seen = True
            if now <= when <= cutoff:
                peak = temp if peak is None else max(peak, temp)

    if peak is None and not timed_seen:
        temps = []
        for entry in forecast[:horizon_hours]:
            if isinstance(entry, dict) and entry.get("temperature") is not None:
                try:
                    temps.append(float(entry["temperature"]))
                except (TypeError, ValueError):
                    pass
        peak = max(temps) if temps else None

    return peak


def heat_outlook(
    forecast,
    now: datetime,
    comfort_c: float,
    unit,
    span_c: float = 6.0,
    horizon_hours: int = HORIZON_HOURS,
) -> float:
    """Proximity-weighted upcoming heat above comfort, from 0 to 1."""
    if not isinstance(forecast, list) or not forecast:
        return 0.0

    comparison_tz = _comparison_timezone(now)
    now = _normalize_datetime(now, comparison_tz)
    cutoff = now + timedelta(hours=horizon_hours)
    total = 0.0
    weight = 0.0

    for entry in forecast:
        if not isinstance(entry, dict):
            continue
        try:
            temp_c = to_celsius(float(entry.get("temperature")), unit)
        except (TypeError, ValueError):
            continue

        when = _parse_dt(entry.get("datetime"), comparison_tz)
        if when is None or not (now <= when <= cutoff):
            continue

        hours_away = (when - now).total_seconds() / 3600.0
        proximity = max(0.0, 1.0 - hours_away / horizon_hours)
        excess = max(0.0, temp_c - comfort_c)
        total += min(excess / span_c, 1.0) * proximity
        weight += proximity

    return total / weight if weight else 0.0


def precool_opportunity(
    forecast,
    price_series,
    now: datetime,
    comfort_c: float,
    unit,
    horizon_hours: int = HORIZON_HOURS,
) -> float:
    """Return how strongly it is worth pre-cooling now, from 0 to 1."""
    if not isinstance(forecast, list) or not forecast:
        return 0.0

    comparison_tz = _comparison_timezone(now)
    now = _normalize_datetime(now, comparison_tz)
    cutoff = now + timedelta(hours=horizon_hours)
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

        when = _parse_dt(entry.get("datetime"), comparison_tz)
        if when is None or not (soon <= when <= cutoff):
            continue

        excess = max(0.0, temp_c - comfort_c)
        if excess > 0:
            later_heat = max(later_heat, excess)
            later_hours.append(when)

    if later_heat <= 0.0 or not later_hours:
        return 0.0

    heat_score = min(later_heat / 6.0, 1.0)
    if price_series is None:
        return heat_score

    now_price = None
    hot_prices = []
    for when, price in price_series:
        if price is None or not isinstance(when, datetime):
            continue
        when = _normalize_datetime(when, comparison_tz)
        if when <= soon:
            now_price = price if now_price is None else min(now_price, price)
        if any(abs((when - hot_hour).total_seconds()) < 1800 for hot_hour in later_hours):
            hot_prices.append(price)

    if now_price is None or not hot_prices:
        return heat_score * 0.5

    hot_price = sum(hot_prices) / len(hot_prices)
    if now_price >= hot_price:
        return 0.0

    saving = min((hot_price - now_price) / max(hot_price, 0.01), 1.0)
    return heat_score * (0.5 + 0.5 * saving)

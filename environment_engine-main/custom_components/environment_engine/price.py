"""Price-forecast helpers (pure, testable).

Normalizes a spot-price forecast into an upcoming price series, then derives a
smooth expensiveness *rank* (percentile within today) and the cheapest upcoming
*window* for load-shifted pre-cooling. Handles several integration shapes:
  * Elpriset just nu: today/tomorrow/forecast lists of {time_start, SEK_per_kWh}
  * Nordpool: raw_today/raw_tomorrow lists of {start, value}
  * plain hourly today/tomorrow float lists
Slot granularity (hourly, 15-min, ...) is detected, so windows are in real hours.
"""
from __future__ import annotations
from datetime import datetime, timedelta


def _as_dt(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _entry(item):
    """(-> datetime|None, value|None) for one forecast list item (dict or float)."""
    if isinstance(item, dict):
        dt = _as_dt(item.get("time_start") if "time_start" in item else item.get("start"))
        raw = item.get("SEK_per_kWh", item.get("value"))
        return dt, _as_float(raw)
    return None, _as_float(item)


def _raw_list(attributes):
    """Pull the best available forecast list (combined today+tomorrow) from attrs."""
    if isinstance(attributes.get("forecast"), list):
        return attributes["forecast"]
    for today_key, tomorrow_key in (("raw_today", "raw_tomorrow"), ("today", "tomorrow")):
        if isinstance(attributes.get(today_key), list):
            combined = list(attributes[today_key])
            if isinstance(attributes.get(tomorrow_key), list):
                combined += attributes[tomorrow_key]
            return combined
    return []


def _all_points(attributes, now):
    out, floats = [], []
    for item in _raw_list(attributes) if isinstance(attributes, dict) else []:
        dt, val = _entry(item)
        if val is None:
            continue
        if dt is not None:
            out.append((dt, val))
        else:
            floats.append(val)
    if not out and floats:  # hourly float fallback, anchored to local midnight
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        out = [(midnight + timedelta(hours=h), v) for h, v in enumerate(floats)]
    out.sort(key=lambda x: x[0])
    return out


def price_series(attributes, now):
    """Upcoming [(start_dt, value)] from the current slot onward."""
    cutoff = now - timedelta(hours=1)
    return [(t, v) for t, v in _all_points(attributes, now) if t >= cutoff]


def day_values(attributes, now):
    """All of *today's* price values -- the distribution to rank the current price in."""
    today = now.date()
    return [v for t, v in _all_points(attributes, now) if t.date() == today]


def price_rank(current, values):
    """Percentile 0..1 of `current` within `values` (0 = cheapest, 1 = priciest)."""
    if current is None or not values:
        return None
    below = sum(1 for v in values if v < current)
    equal = sum(1 for v in values if v == current)
    return (below + 0.5 * equal) / len(values)  # midpoint rank handles price ties


def _slot_hours(series):
    deltas = [(series[i + 1][0] - series[i][0]).total_seconds() / 3600.0 for i in range(min(len(series) - 1, 6))]
    deltas = [d for d in deltas if d > 0]
    return min(deltas) if deltas else 1.0


def cheapest_window(series, now, duration_hours=2.0, horizon_hours=8.0):
    """Start datetime of the cheapest contiguous duration-hour block within the next
    horizon_hours, or None. Slot-granularity aware."""
    if not series:
        return None
    horizon_end = now + timedelta(hours=horizon_hours)
    window = [(t, v) for t, v in series if now - timedelta(hours=1) <= t <= horizon_end]
    if not window:
        return None
    n = max(1, int(round(duration_hours / _slot_hours(window))))
    if len(window) < n:
        return window[0][0]
    best_start, best_avg = None, None
    for i in range(len(window) - n + 1):
        block = window[i:i + n]
        avg = sum(v for _, v in block) / n
        if best_avg is None or avg < best_avg:
            best_avg, best_start = avg, block[0][0]
    return best_start


def in_cheapest_window(series, now, duration_hours=2.0, horizon_hours=8.0):
    """True when *now* falls inside the cheapest upcoming window."""
    start = cheapest_window(series, now, duration_hours, horizon_hours)
    return start is not None and start <= now < start + timedelta(hours=duration_hours)

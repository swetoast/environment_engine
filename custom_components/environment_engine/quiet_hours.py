"""Quiet hours: a nightly window where the compressor is held back.

During quiet hours the engine prefers moving air (the AC's own fan_only, plus any
standalone fan) over running the compressor, so a bedroom stays quiet at night. It is
not a hard block: if the room passes the configured "too hot" line, comfort wins and
cooling resumes -- quiet hours should never let you cook.
"""
from __future__ import annotations
from datetime import time


def parse_time(value) -> time | None:
    """'22:00' / '22:00:00' / a time -> time, else None."""
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        parts = value.split(":")
        try:
            hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return time(hour, minute)
        except (ValueError, IndexError):
            return None
    return None


def in_quiet_hours(now: time | None, start, end) -> bool:
    """True when `now` falls inside the quiet window. Handles windows that wrap
    midnight (e.g. 22:00 -> 07:00). An empty window (start == end) is never quiet."""
    start_t, end_t = parse_time(start), parse_time(end)
    if now is None or start_t is None or end_t is None or start_t == end_t:
        return False
    if start_t < end_t:
        return start_t <= now < end_t
    return now >= start_t or now < end_t  # wraps past midnight

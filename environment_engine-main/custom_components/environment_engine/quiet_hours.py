"""Quiet hours: a nightly window where the compressor is held back.

During quiet hours the engine prefers moving air (the AC's own fan_only, plus any
standalone fan) over running the compressor, so a bedroom stays quiet at night. It is
not a hard block: if the room passes the configured "too hot" line, comfort wins and
cooling resumes -- quiet hours should never let you cook.
"""
from __future__ import annotations
import re
from datetime import time


def parse_time(value) -> time | None:
    """Normalise whatever Hom Assistant's TimeSelector hands us into a `time`.

    Depending on version and transport that can be a `time`, a `'HH:MM'` / `'HH:MM:SS'`
    string, or a dict like `{'hour': 22, 'minute': 0, 'second': 0}`. All three (and the
    stringified dict, which is what we get if a dict was coerced with `str()` before being
    stored) must resolve, or quiet hours silently never triggers. Anything unrecognised -> None.
    """
    if isinstance(value, time):
        return value.replace(tzinfo=None)  # compared against a naive local time()
    if isinstance(value, dict):
        try:
            hour = int(value["hour"])
            minute = int(value.get("minute", 0))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return time(hour, minute)
        except (KeyError, TypeError, ValueError):
            return None
        return None
    if isinstance(value, str):
        text = value.strip()
        # A dict that was str()'d on the way into storage, e.g. "{'hour': 22, 'minute': 0}".
        if text.startswith("{"):
            match = re.search(r"['\"]hour['\"]\s*:\s*(\d+).*?['\"]minute['\"]\s*:\s*(\d+)", text)
            if match:
                hour, minute = int(match.group(1)), int(match.group(2))
                return time(hour, minute) if 0 <= hour <= 23 and 0 <= minute <= 59 else None
            return None
        parts = text.split(":")
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


def minutes_until(now: time | None, when) -> float | None:
    """Minutes from `now` until the next time the clock reads `when` (0..1440)."""
    target = parse_time(when)
    if now is None or target is None:
        return None
    return ((target.hour * 60 + target.minute) - (now.hour * 60 + now.minute + now.second / 60.0)) % 1440


def window_minutes(start, end) -> float | None:
    """Length of the quiet window in minutes, or None when it is unset or empty."""
    start_t, end_t = parse_time(start), parse_time(end)
    if start_t is None or end_t is None or start_t == end_t:
        return None
    return ((end_t.hour * 60 + end_t.minute) - (start_t.hour * 60 + start_t.minute)) % 1440

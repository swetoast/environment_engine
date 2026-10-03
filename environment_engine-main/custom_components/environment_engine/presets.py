"""Map the engine's speed tiers onto a device's own preset modes.

An air purifier is not a fan. It usually exposes named preset modes (Auto, Silent,
Favorite, Sleep, Turbo...) rather than a raw percentage, and driving it by percentage
either does nothing useful or fights the device's own logic. This resolves our
low/medium/high tier to whatever the device actually offers; when nothing matches,
it returns None and the caller falls back to a percentage.
"""
from __future__ import annotations

_SYNONYMS = {
    "low": ("low", "silent", "sleep", "night", "quiet", "gentle"),
    "medium": ("medium", "favorite", "favourite", "standard", "normal", "medium speed"),
    "high": ("high", "max", "maximum", "turbo", "strong", "boost", "powerful"),
}


_FRACTION = {"low": 0.33, "medium": 0.66, "high": 1.0}


def preset_fraction(preset) -> float:
    """Airflow (0..1) a running purifier's preset stands for; a middle value when the
    preset is unknown or absent (Auto, or a plain on/off unit)."""
    name = str(preset).strip().lower() if preset else ""
    for tier, names in _SYNONYMS.items():
        if name in names:
            return _FRACTION[tier]
    return 0.66


def preset_for_speed(available, speed: str | None) -> str | None:
    """The device's own preset name for our speed tier, or None if it has no match."""
    if not available or not speed:
        return None
    lookup = {str(mode).strip().lower(): mode for mode in available}
    for candidate in _SYNONYMS.get(speed, ()):
        if candidate in lookup:
            return lookup[candidate]
    return None

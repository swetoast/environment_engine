"""Entity-list normalization.

Every config slot now stores a *list* of entity ids (the config-flow selectors are
multi-select), so a room can have several fans, sensors, etc. `as_list` tolerates
the old single-string form and empty values so readers never special-case them.
"""
from __future__ import annotations


def as_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v]
    return [value]

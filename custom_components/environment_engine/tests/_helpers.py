"""Shared test helpers.

`make_options` builds an EngineOptions with sensible defaults, so each test names
only the fields it actually cares about. Because every EngineOptions field now has
a default, adding a new option never touches existing tests.
"""
from custom_components.environment_engine.options import EngineOptions


def make_options(**overrides) -> EngineOptions:
    return EngineOptions(**overrides)

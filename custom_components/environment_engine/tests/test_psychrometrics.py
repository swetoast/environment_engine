"""Dew-point (Magnus formula) used by the condensation guard."""
from custom_components.environment_engine.psychrometrics import dew_point


def test_humid_room_has_high_dew_point():
    assert 18.5 < dew_point(24.0, 75.0) < 20.0


def test_dry_room_has_low_dew_point():
    assert dew_point(24.0, 40.0) < 11.0


def test_missing_or_invalid_inputs_return_none():
    assert dew_point(None, 50) is None
    assert dew_point(24.0, None) is None
    assert dew_point(24.0, 0) is None

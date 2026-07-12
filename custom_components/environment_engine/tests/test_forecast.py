"""Forecast peak + weighted heat outlook (trend-aware precool)."""
from datetime import datetime, timedelta, timezone
from custom_components.environment_engine.forecast import heat_outlook, upcoming_peak

NOW = datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc)


def _fc(*pairs):  # (hours_from_now, temp_c)
    return [{"datetime": (NOW + timedelta(hours=h)).isoformat(), "temperature": t} for h, t in pairs]


def test_peak_picks_max_in_horizon():
    assert upcoming_peak(_fc((1, 22), (3, 31), (5, 28)), NOW) == 31


def test_sustained_soon_heat_scores_higher_than_lone_distant_spike():
    comfort = 22.0
    sustained = heat_outlook(_fc((1, 30), (2, 31), (3, 30), (4, 29)), NOW, comfort, "°C")
    lone = heat_outlook(_fc((7, 33), (1, 22), (2, 22)), NOW, comfort, "°C")
    assert sustained > lone


def test_no_heat_above_comfort_is_zero():
    assert heat_outlook(_fc((1, 20), (2, 19)), NOW, 22.0, "°C") == 0.0


def test_fahrenheit_converted():
    # 95F ~ 35C, well above 22C comfort -> positive
    assert heat_outlook(_fc((1, 95), (2, 96)), NOW, 22.0, "°F") > 0.3


def test_empty_forecast_zero():
    assert heat_outlook([], NOW, 22.0, "°C") == 0.0

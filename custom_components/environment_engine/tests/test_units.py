"""Temperature unit normalization, including the Fahrenheit thermal bug."""
from _helpers import make_options
from custom_components.environment_engine.thermal_memory import ThermalMemory
from custom_components.environment_engine.evaluators import evaluate_thermal
from custom_components.environment_engine.units import from_celsius, to_celsius

OPTS = make_options()


def test_to_celsius_variants():
    assert round(to_celsius(77, "°F"), 2) == 25.0
    assert round(to_celsius(77, "fahrenheit"), 2) == 25.0
    assert to_celsius(25, "°C") == 25
    assert round(to_celsius(298.15, "K"), 2) == 25.0
    assert to_celsius(None, "°F") is None
    assert to_celsius(20, None) == 20  # unknown unit -> assume celsius


def test_from_celsius_roundtrip():
    assert round(from_celsius(25, "°F"), 2) == 77.0
    assert round(from_celsius(to_celsius(68, "°F"), "°F"), 2) == 68.0
    assert from_celsius(22, "°C") == 22


def test_fahrenheit_sensor_would_break_thermal_without_conversion():
    mem = ThermalMemory()
    raw_f = 72.0  # a comfortable 22.2 C, but raw 72 looks scorching to the C math
    # Without conversion: 72 treated as Celsius -> pinned at max cooling
    unconverted = evaluate_thermal(_S(72.0), mem, 0.0, 0.0, 0.0, OPTS.target)
    assert unconverted.confidence >= 0.99
    # With conversion: 72F -> ~22.2C -> essentially no thermal pressure
    converted = evaluate_thermal(_S(to_celsius(raw_f, "°F")), mem, 0.0, 0.0, 0.0, OPTS.target)
    assert converted.confidence < 0.1


class _S:
    """Minimal snapshot stand-in for the thermal evaluator."""
    def __init__(self, indoor):
        self.feels_like = None
        self.indoor_temp = indoor

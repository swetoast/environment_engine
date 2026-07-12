"""Adaptive learning now tracks drying only -- cooling is measured by the thermal model."""
from custom_components.environment_engine.adaptive_learning import AdaptiveLearning
from custom_components.environment_engine.const import STRATEGY_DEHUMIDIFY


class _S:
    def __init__(self, indoor=24.0, humidity=60.0):
        self.indoor_temp = indoor
        self.humidity = humidity


class _D:
    def __init__(self, strategy):
        self.strategy = strategy


def test_circulation_is_not_counted_as_a_failed_cooling_attempt():
    """Regression: a fan doesn't lower air temperature, so counting circulation as a
    cooling attempt logged endless 'failures' and biased the engine against ever cooling.
    Cooling is now measured properly by ThermalModel, with the loads controlled for."""
    learning = AdaptiveLearning()
    assert not hasattr(learning.state, "cooling_failures")
    assert not hasattr(learning, "cooling_bias")


def test_drying_success_is_still_learned():
    learning = AdaptiveLearning()
    for _ in range(6):
        learning.update(_S(humidity=60.0), _D(STRATEGY_DEHUMIDIFY), _S(humidity=58.0))
    assert learning.state.drying_successes == 6
    assert learning.drying_bias() > 0


def test_drying_failure_biases_down():
    learning = AdaptiveLearning()
    for _ in range(6):
        learning.update(_S(humidity=60.0), _D(STRATEGY_DEHUMIDIFY), _S(humidity=62.0))
    assert learning.state.drying_failures == 6
    assert learning.drying_bias() < 0


def test_bias_needs_evidence():
    learning = AdaptiveLearning()
    learning.update(_S(humidity=60.0), _D(STRATEGY_DEHUMIDIFY), _S(humidity=58.0))
    assert learning.drying_bias() == 0.0  # one sample is not a pattern


def test_reset_clears_state():
    learning = AdaptiveLearning()
    for _ in range(6):
        learning.update(_S(humidity=60.0), _D(STRATEGY_DEHUMIDIFY), _S(humidity=58.0))
    learning.reset()
    assert learning.state.drying_successes == 0

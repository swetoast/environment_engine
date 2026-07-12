"""resolved_options must build from defaults and merge data/options correctly."""
from custom_components.environment_engine.const import DEFAULTS, OPT_TARGET_TEMPERATURE
from custom_components.environment_engine.options import resolved_options


def test_defaults_only_builds_cleanly():
    o = resolved_options({}, {})  # the setup path that was crashing
    assert o.target_temperature == DEFAULTS[OPT_TARGET_TEMPERATURE]
    assert o.outdoor_aqi_threshold == 100
    assert o.sleep_lux == 5


def test_options_override_data_override_defaults():
    o = resolved_options({OPT_TARGET_TEMPERATURE: 20}, {OPT_TARGET_TEMPERATURE: 18})
    assert o.target_temperature == 18  # options win over data win over defaults


def test_clamps_apply():
    o = resolved_options({}, {"target_temperature": 99, "dewpoint_margin": 99})
    assert o.target_temperature == 30      # clamped to device-sane max
    assert o.dewpoint_margin == 6.0        # clamped

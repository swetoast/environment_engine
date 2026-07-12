"""supported_features decoding (uses literal-bit fallback when HA enums absent)."""
from custom_components.environment_engine.features import climate_features, cover_features, fan_features


class _State:
    def __init__(self, state="on", **attrs):
        self.state = state
        self.attributes = attrs


def test_fan_49_is_set_speed_no_preset():
    # Toast's purifier: 49 = SET_SPEED(1) | TURN_OFF(16) | TURN_ON(32)
    f = fan_features(_State(supported_features=49, percentage=100, percentage_step=33.3))
    assert f.set_speed is True
    assert f.preset_mode is False


def test_fan_preset_only_device():
    f = fan_features(_State(supported_features=8, preset_modes=["auto", "sleep"]))
    assert f.set_speed is False
    assert f.preset_mode is True


def test_fan_without_bitmask_infers_from_percentage():
    assert fan_features(_State(percentage_step=33.3)).set_speed is True
    assert fan_features(_State()).set_speed is False


def test_climate_385_supports_target_and_turn_off():
    # Toast's AC: 385 = TARGET_TEMPERATURE(1) | TURN_OFF(128) | TURN_ON(256)
    c = climate_features(_State(state="fan_only", supported_features=385))
    assert c.target_temperature is True
    assert c.turn_off is True


def test_climate_without_target_temperature():
    c = climate_features(_State(supported_features=8))  # FAN_MODE only
    assert c.target_temperature is False


def test_climate_missing_bitmask_assumes_capable():
    assert climate_features(_State(state="off")).target_temperature is True


def test_cover_position_only():
    c = cover_features(_State(state="open", supported_features=4))  # SET_POSITION only
    assert c.open_close is False
    assert c.set_position is True


def test_cover_open_close():
    c = cover_features(_State(state="open", supported_features=3))  # OPEN|CLOSE
    assert c.open_close is True
    assert c.set_position is False

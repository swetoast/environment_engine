"""A purifier is driven as a purifier (preset modes), and the ionizer actually runs."""
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.const import ACTION_NONE, ACTION_OFF, ACTION_ON
from custom_components.environment_engine.presets import preset_for_speed
from custom_components.environment_engine.resolvers import resolve_purifier

XIAOMI = ["Auto", "Silent", "Favorite", "Fan"]
LEVOIT = ["auto", "sleep", "low", "medium", "high"]


def test_preset_maps_to_the_devices_own_names():
    assert preset_for_speed(XIAOMI, "low") == "Silent"
    assert preset_for_speed(XIAOMI, "medium") == "Favorite"
    assert preset_for_speed(LEVOIT, "high") == "high"


def test_no_match_falls_back_to_percentage():
    assert preset_for_speed(XIAOMI, "high") is None     # caller uses a percentage
    assert preset_for_speed([], "low") is None
    assert preset_for_speed(LEVOIT, None) is None


def _caps(ionizer=True):
    return Capabilities(climate=False, temperature=True, humidity=False, weather=False, occupancy=False,
                        windows=False, pricing=False, air_quality=True, blinds=False, illuminance=False,
                        fan=False, purifier=True, humidifier=False, ionizer=ionizer, ventilation=False,
                        smoke=False, lightning=False, outlet_overload=False)


class _AQ:
    def __init__(self, pressure, recommended=True, seal=False):
        self.pressure = pressure
        self.purifier_recommended = recommended
        self.seal = seal
        self.reason = "air quality"


def test_ionizer_runs_with_the_purifier_by_default():
    action, _, ionizer, _ = resolve_purifier(_caps(), make_options(), {"air_quality": _AQ(0.5)})
    assert action == ACTION_ON and ionizer == ACTION_ON  # no unreachable surge needed


def test_surge_mode_waits_for_heavy_pollution():
    opts = make_options(ionizer_mode="surge")
    _, _, low, _ = resolve_purifier(_caps(), opts, {"air_quality": _AQ(0.5)})
    _, _, high, _ = resolve_purifier(_caps(), opts, {"air_quality": _AQ(0.7)})
    assert low == ACTION_OFF and high == ACTION_ON


def test_never_mode_keeps_it_off():
    _, _, ionizer, _ = resolve_purifier(_caps(), make_options(ionizer_mode="never"), {"air_quality": _AQ(0.9)})
    assert ionizer == ACTION_OFF


def test_no_ionizer_device_means_no_action():
    _, _, ionizer, _ = resolve_purifier(_caps(ionizer=False), make_options(), {"air_quality": _AQ(0.9)})
    assert ionizer == ACTION_NONE

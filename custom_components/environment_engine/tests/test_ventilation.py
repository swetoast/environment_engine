"""CO2-driven fresh-air ventilation (a purifier can't remove CO2)."""
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.const import ACTION_NONE, ACTION_OFF, ACTION_ON
from custom_components.environment_engine.resolvers import resolve_ventilation
from custom_components.environment_engine.snapshot import Snapshot


def _opts():
    return make_options()


def _caps(vent=True):
    base = dict(climate=False, temperature=False, humidity=False, weather=False, occupancy=False, windows=False,
                pricing=False, air_quality=False, blinds=False, illuminance=False, fan=False, purifier=False,
                humidifier=False, ionizer=False, ventilation=vent, smoke=False, lightning=False, outlet_overload=False)
    return Capabilities(**base)


def _snap(co2):
    return Snapshot(indoor_temp=22.0, humidity=50.0, outdoor_temp=18.0, occupancy=True, window_open=False,
                    energy_price=None, co2=co2, voc=None, hvac_mode="off")


class _AQ:
    def __init__(self, seal=False, indoor_event=False):
        self.seal = seal
        self.indoor_event = indoor_event


def _ev(seal=False, indoor_event=False):
    return {"air_quality": _AQ(seal, indoor_event)}


def test_high_co2_brings_fresh_air():
    action, _ = resolve_ventilation(_snap(1200), _caps(), _opts(), _ev())
    assert action == ACTION_ON


def test_low_co2_stops_ventilation():
    action, _ = resolve_ventilation(_snap(800), _caps(), _opts(), _ev())
    assert action == ACTION_OFF


def test_deadband_holds_between_thresholds():
    action, _ = resolve_ventilation(_snap(900), _caps(), _opts(), _ev())
    assert action == ACTION_NONE  # 850..1000 -> hold


def test_seal_forces_ventilation_off():
    action, _ = resolve_ventilation(_snap(1500), _caps(), _opts(), _ev(seal=True))
    assert action == ACTION_OFF  # don't pull in bad outdoor air


def test_no_ventilation_capability_is_noop():
    action, _ = resolve_ventilation(_snap(1500), _caps(vent=False), _opts(), _ev())
    assert action == ACTION_NONE


def test_indoor_particle_event_airs_out():
    # clean outdoor + indoor particle event -> ventilate to clear it (even at low CO2)
    action, _ = resolve_ventilation(_snap(500), _caps(), _opts(), _ev(indoor_event=True))
    assert action == ACTION_ON

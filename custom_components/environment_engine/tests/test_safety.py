"""Safety holds. Lightning is computed upstream (see test_lightning); here we only
verify the block reacts to the snapshot's lightning_hold flag."""
from _helpers import make_options
from custom_components.environment_engine.capabilities import Capabilities
from custom_components.environment_engine.evaluators import evaluate_safety
from custom_components.environment_engine.snapshot import Snapshot


def _opts():
    return make_options()


def _caps(**kw):
    base = dict(climate=False, temperature=False, humidity=False, weather=False, occupancy=False, windows=False,
                pricing=False, air_quality=False, blinds=False, illuminance=False, fan=False, purifier=False,
                humidifier=False, ionizer=False, ventilation=False, smoke=False, lightning=False, outlet_overload=False)
    base.update(kw)
    return Capabilities(**base)


def _snap(**kw):
    d = dict(indoor_temp=22.0, humidity=50.0, outdoor_temp=18.0, occupancy=True, window_open=False,
             energy_price=None, co2=None, voc=None, hvac_mode="cool")
    d.update(kw)
    return Snapshot(**d)


def test_lightning_hold_blocks():
    r = evaluate_safety(_snap(lightning_hold=True, lightning_closest=8.0, lightning_strikes=4), _caps(lightning=True), _opts())
    assert r.blocked is True and "8 km" in r.reason and "4 strikes" in r.reason


def test_no_lightning_hold_does_not_block():
    assert evaluate_safety(_snap(lightning_hold=False), _caps(lightning=True), _opts()).blocked is False


def test_lightning_disabled_ignores_hold():
    # capability off (safety toggle off) -> even a hold is ignored
    assert evaluate_safety(_snap(lightning_hold=True, lightning_closest=2.0, lightning_strikes=9), _caps(lightning=False), _opts()).blocked is False


def test_smoke_blocks():
    assert evaluate_safety(_snap(smoke_detected=True), _caps(smoke=True), _opts()).blocked is True

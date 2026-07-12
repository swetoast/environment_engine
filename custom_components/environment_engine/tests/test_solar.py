"""Solar shading, incl. low-sun (glare) geometry awareness."""
from custom_components.environment_engine.evaluators import evaluate_solar
from _helpers import make_options
from custom_components.environment_engine.snapshot import Snapshot


def _opts():
    return make_options()


def _snap(**kw):
    d = dict(indoor_temp=24.0, humidity=50.0, outdoor_temp=18.0, occupancy=True, window_open=False,
             energy_price=None, co2=None, voc=None, hvac_mode="off", sun_up=True, lux=700.0)
    d.update(kw)
    return Snapshot(**d)


def test_high_sun_uses_full_threshold():
    # lux 700 < 1000 threshold, sun high -> no lux shading
    assert evaluate_solar(_snap(lux=700.0, sun_elevation=60.0), _opts()).shading_recommended is False


def test_low_sun_shades_earlier():
    # same lux 700, but low sun halves the threshold (~500) -> now shades for glare
    r = evaluate_solar(_snap(lux=700.0, sun_elevation=10.0), _opts())
    assert r.shading_recommended is True and "low-angle" in r.reason


def test_sun_down_no_shading():
    assert evaluate_solar(_snap(sun_up=False), _opts()).shading_recommended is False

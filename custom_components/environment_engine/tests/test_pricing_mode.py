"""Fixed-price ('fast pris') mode: all price-shaping disabled, comfort-first."""
from _helpers import make_options
from custom_components.environment_engine.evaluators import evaluate_energy
from custom_components.environment_engine.snapshot import Snapshot


def _opts(mode="spot"):
    return make_options(pricing_mode=mode)


def _snap(price, rank):
    return Snapshot(indoor_temp=24.0, humidity=50.0, outdoor_temp=20.0, occupancy=True, window_open=False,
                    energy_price=price, co2=None, voc=None, hvac_mode="off", price_rank=rank, price_average=0.3)


def test_fixed_price_zeroes_the_penalty_even_when_expensive():
    r = evaluate_energy(_snap(1.5, 0.95), _opts("fixed"))
    assert r.penalty == 0.0 and r.expensive is False and "fixed" in r.reason.lower()


def test_spot_mode_still_penalizes_expensive():
    r = evaluate_energy(_snap(1.5, 0.95), _opts("spot"))
    assert r.expensive is True and r.penalty > 0


def test_fixed_price_ignores_missing_forecast_gracefully():
    # no rank/avg needed -- fixed short-circuits before any price math
    r = evaluate_energy(_snap(None, None), _opts("fixed"))
    assert r.penalty == 0.0 and r.expensive is False

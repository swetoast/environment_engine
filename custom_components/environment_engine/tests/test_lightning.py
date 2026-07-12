"""Dynamic lightning hold (mirrors the Blitzortung template)."""
from custom_components.environment_engine.lightning import lightning_hold


def test_no_strikes_no_hold():
    assert lightning_hold([], [], 30) == (False, None, 0)


def test_very_close_recent_single_strike_holds():
    hold, closest, strikes = lightning_hold([1.0], [30], 30)
    assert hold is True and closest == 1.0 and strikes == 1


def test_single_distant_strike_fades_fast():
    # one strike at 5 km, 60 s old -> low intensity -> short window -> already released
    assert lightning_hold([5.0], [60], 30)[0] is False


def test_beyond_max_react_never_holds():
    assert lightning_hold([45.0], [10], 30)[0] is False


def test_intense_storm_holds_wider_and_longer():
    dists = [20, 25, 30, 22, 40, 18, 35, 28]
    ages = [300, 120, 90, 60, 200, 50, 150, 80]
    hold, closest, strikes = lightning_hold(dists, ages, 30)
    assert hold is True and strikes == 8 and closest == 18


def test_hold_releases_as_strikes_age_out():
    dists = [5, 6, 7, 8, 9]
    fresh = lightning_hold(dists, [30, 40, 50, 60, 70], 30)[0]
    stale = lightning_hold(dists, [4000, 4100, 4200, 4300, 4400], 30)[0]
    assert fresh is True and stale is False


def test_tolerates_unparseable_strike_readings():
    # A geo_location entity with a junk state must not take down the safety path.
    assert lightning_hold([None], [0], 30) == (False, None, 0)
    hold, closest, strikes = lightning_hold([5.0, None], [10, None], 30)
    assert strikes == 1 and closest == 5.0

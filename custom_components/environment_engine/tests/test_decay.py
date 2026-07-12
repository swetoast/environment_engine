"""Peak-hold with exponential decay (air-quality post-event recovery)."""
from custom_components.environment_engine.decay import PeakDecay


def test_spike_then_decays_over_half_life():
    d = PeakDecay()
    assert d.update(1.0, 0, 600) == 1.0          # spike
    assert abs(d.update(0.05, 600, 600) - 0.5) < 0.02   # one half-life -> ~0.5
    assert abs(d.update(0.05, 1200, 600) - 0.25) < 0.02  # two -> ~0.25


def test_new_higher_reading_resets_peak():
    d = PeakDecay()
    d.update(0.5, 0, 600)
    assert d.update(0.9, 60, 600) == 0.9


def test_steady_reading_tracks_value():
    d = PeakDecay()
    d.update(0.4, 0, 600)
    assert abs(d.update(0.4, 600, 600) - 0.4) < 1e-9


def test_zero_half_life_disables_hold():
    d = PeakDecay()
    d.update(1.0, 0, 0)
    assert d.update(0.1, 100, 0) == 0.1


def test_never_negative():
    d = PeakDecay()
    assert d.update(-5.0, 0, 600) == 0.0


def test_outdoor_seal_holds_through_lull_then_releases():
    # spike above threshold, dip below during a lull -> still held above; long clear -> released
    seal = PeakDecay()
    threshold, hl = 100, 600
    assert seal.update(180, 0, hl) >= threshold          # spike -> sealed
    assert seal.update(60, 180, hl) >= threshold         # 3-min lull -> still sealed
    assert seal.update(60, 480, hl) >= threshold         # 8-min lull -> still sealed
    assert seal.update(20, 1200, hl) < threshold         # truly cleared -> released


def test_presence_hold_survives_brief_stillness_then_releases():
    p = PeakDecay()
    hl = 300  # 5-min hold
    assert p.update(1.0, 0, hl) >= 0.5      # motion -> home
    assert p.update(0.0, 120, hl) >= 0.5    # still 2 min -> home
    assert p.update(1.0, 200, hl) >= 0.5    # motion again resets
    assert p.update(0.0, 900, hl) < 0.5     # long absence -> away

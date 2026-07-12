"""Device on-time accumulator (filter-life / maintenance)."""
from custom_components.environment_engine.runtime import RuntimeTracker


def test_accumulates_active_channels():
    t = RuntimeTracker()
    t.update(0, {"climate"})
    t.update(3600, {"climate", "purifier"})   # +1h climate; purifier starts now
    t.update(7200, {"purifier"})              # +1h both
    assert t.hours("climate") == 2.0
    assert t.hours("purifier") == 1.0


def test_first_update_sets_baseline_no_time():
    t = RuntimeTracker()
    t.update(1000, {"climate"})
    assert t.hours("climate") == 0.0


def test_idle_channel_does_not_accumulate():
    t = RuntimeTracker()
    t.update(0, set())
    t.update(3600, set())
    assert t.hours("climate") == 0.0


def test_seed_restores_total_so_it_persists_across_restart():
    t = RuntimeTracker()
    t.seed("purifier", 0.77)                 # restored from the sensor after a restart
    assert t.hours("purifier") == 0.77
    t.update(0, {"purifier"})
    t.update(3600, {"purifier"})             # +1h this session
    assert t.hours("purifier") == 1.77       # total = restored + session (no reset)


def test_seed_does_not_lower_an_existing_total():
    t = RuntimeTracker()
    t.update(0, {"climate"}); t.update(7200, {"climate"})  # 2h this session
    t.seed("climate", 0.5)                    # a stale/lower restore must not shrink it
    assert t.hours("climate") == 2.0


def test_daily_usage_rolls_over_at_midnight():
    t = RuntimeTracker()
    t.update(0, {"climate"}, "2026-07-04")
    t.update(3600, {"climate"}, "2026-07-04")      # 1h today
    assert t.today_hours("climate") == 1.0
    t.update(7200, {"climate"}, "2026-07-05")      # new day -> daily resets
    assert t.today_hours("climate") == 0.0
    assert t.hours("climate") == 2.0               # lifetime keeps counting


def test_seed_today_only_restores_same_day():
    t = RuntimeTracker()
    t.update(0, set(), "2026-07-05")
    t.seed_today("climate", 3.0, "2026-07-04")     # yesterday's value -> ignored
    assert t.today_hours("climate") == 0.0
    t.seed_today("climate", 1.5, "2026-07-05")     # today's -> restored
    assert t.today_hours("climate") == 1.5


def test_lifetime_and_today_tracked_independently():
    t = RuntimeTracker()
    t.seed("purifier", 100.0)                      # restored lifetime (filter life)
    t.update(0, {"purifier"}, "2026-07-04")
    t.update(1800, {"purifier"}, "2026-07-04")     # +0.5h
    assert t.hours("purifier") == 100.5
    assert t.today_hours("purifier") == 0.5

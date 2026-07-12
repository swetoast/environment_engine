"""Price-forecast helpers against the real Elpriset shape (15-min dict slots)."""
from datetime import datetime, timedelta, timezone
from _helpers import make_options
from custom_components.environment_engine.price import (
    price_series, day_values, price_rank, cheapest_window, in_cheapest_window,
)
from custom_components.environment_engine.evaluators import evaluate_energy
from custom_components.environment_engine.snapshot import Snapshot

TZ = timezone(timedelta(hours=2))


def _slot(h, m, v):
    st = datetime(2026, 7, 4, h, m, tzinfo=TZ)
    return {"time_start": st.isoformat(), "time_end": (st + timedelta(minutes=15)).isoformat(), "SEK_per_kWh": v}


# cheap midday, pricey evening -- Elpriset style
TODAY = ([_slot(hh, mm, 0.11) for hh in (12, 13, 14, 15) for mm in (0, 15, 30, 45)]
         + [_slot(8, 45, 0.10)]
         + [_slot(hh, mm, 0.85) for hh in (19, 20, 21, 22) for mm in (0, 15, 30, 45)]
         + [_slot(18, 30, 0.39), _slot(18, 45, 0.51)])
ATTRS = {"today": TODAY, "forecast": TODAY}
MIDDAY = datetime(2026, 7, 4, 13, 0, tzinfo=TZ)
EVENING = datetime(2026, 7, 4, 18, 30, tzinfo=TZ)


def test_parses_elpriset_dict_slots():
    s = price_series(ATTRS, MIDDAY)
    assert len(s) > 0 and all(isinstance(v, float) for _, v in s)


def test_nordpool_and_float_shapes_also_parse():
    m = datetime(2026, 7, 4, 0, 0, tzinfo=TZ)
    nordpool = {"raw_today": [{"start": (m + timedelta(hours=h)).isoformat(), "value": 0.2} for h in range(24)]}
    assert len(price_series(nordpool, MIDDAY)) > 0
    assert len(price_series({"today": [0.2] * 24}, MIDDAY)) > 0


def test_day_values_is_todays_distribution():
    tv = day_values(ATTRS, MIDDAY)
    assert len(tv) == len(TODAY)


def test_rank_cheap_vs_pricey():
    tv = day_values(ATTRS, MIDDAY)
    assert price_rank(0.11, tv) < 0.5
    assert price_rank(0.85, tv) > 0.75


def test_cheapest_window_is_the_midday_dip():
    s = price_series(ATTRS, MIDDAY)
    start = cheapest_window(s, MIDDAY, duration_hours=2, horizon_hours=8)
    assert 12 <= start.hour <= 15


def test_slot_aware_window_uses_real_hours():
    # 15-min slots -> a 2h window spans 8 slots, not 2; the dip is 2h wide so it fits
    assert in_cheapest_window(price_series(ATTRS, MIDDAY), MIDDAY, 2, 8) is True


def _opts():
    return make_options()


def _snap(price, rank):
    return Snapshot(indoor_temp=24.0, humidity=50.0, outdoor_temp=20.0, occupancy=True, window_open=False,
                    energy_price=price, co2=None, voc=None, hvac_mode="off", price_rank=rank)


def test_energy_rank_expensive_and_cheap():
    assert evaluate_energy(_snap(0.85, 0.9), _opts()).expensive is True
    assert evaluate_energy(_snap(0.11, 0.1), _opts()).penalty == 0.0

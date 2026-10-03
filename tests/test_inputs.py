"""What the engine reads from the outside world, in the shapes real integrations produce.

Each test pins one real data format: a captured Blitzortung storm, Elpriset and Nord Pool
price attributes, weather and air-quality forecasts with local wall-clock times, Fahrenheit
units, and the feature bitmasks real devices report. If an upstream format parse breaks,
it breaks here.
"""
from datetime import datetime, timedelta, timezone

from custom_components.environment_engine.comfort import humidity_penalty, pmv, ppd
from custom_components.environment_engine.executors.common import snap_percentage
from custom_components.environment_engine.features import climate_features, cover_features, fan_features
from custom_components.environment_engine.forecast import (
    _normalize_datetime, heat_outlook, precool_opportunity, upcoming_peak,
)
from custom_components.environment_engine.lightning import D_MAX, T_BASE, T_MAX, lightning_hold
from custom_components.environment_engine.presets import preset_for_speed, preset_fraction
from custom_components.environment_engine.price import cheapest_window, day_values, in_cheapest_window, price_rank, price_series
from custom_components.environment_engine.psychrometrics import dew_point
from custom_components.environment_engine.quiet_hours import in_quiet_hours, parse_time
from custom_components.environment_engine.units import from_celsius, to_celsius
from harness import Clock, Home, State

CEST = timezone(timedelta(hours=2))

# A real capture: 16 geo_location.lightning_strike_* entities near Borås, 2026-09-07 ~21:22Z.
STORM = [
    (30.3, "2026-09-07T21:16:53.773303+00:00"), (49.4, "2026-09-07T21:16:53.357520+00:00"),
    (48.3, "2026-09-07T21:16:53.357534+00:00"), (29.4, "2026-09-07T21:16:53.773222+00:00"),
    (48.9, "2026-09-07T21:16:53.357537+00:00"), (29.8, "2026-09-07T21:16:53.773231+00:00"),
    (32.6, "2026-09-07T21:13:03.836361+00:00"), (33.7, "2026-09-07T21:22:19.335430+00:00"),
    (48.3, "2026-09-07T21:22:19.335496+00:00"), (48.4, "2026-09-07T21:16:53.357534+00:00"),
    (48.0, "2026-09-07T21:16:53.357532+00:00"), (48.7, "2026-09-07T21:16:53.357535+00:00"),
    (47.9, "2026-09-07T21:16:53.357535+00:00"), (49.5, "2026-09-07T21:16:53.357510+00:00"),
    (48.4, "2026-09-07T21:16:53.357539+00:00"), (29.4, "2026-09-07T21:16:53.773222+00:00"),
]
STORM_NOW = datetime(2026, 9, 7, 21, 22, 30, tzinfo=timezone.utc)


def test_lightning_a_real_storm_holds_and_the_hold_expires(monkeypatch):
    # The maths, on the captured distances and ages.
    ages = [STORM_NOW.timestamp() - datetime.fromisoformat(p).timestamp() for _, p in STORM]
    hold, closest, count = lightning_hold([d for d, _ in STORM], ages, 40)
    assert hold is True and abs(closest - 29.4) < 0.1 and count == len(STORM)
    assert lightning_hold([41.0], [10.0], 40)[0] is False            # outside the radius
    assert lightning_hold([D_MAX + 5], [0.0], 40)[0] is False        # beyond what the model reacts to
    assert lightning_hold([29.4], [T_BASE - 60], 40)[0] is True      # inside the base hold
    assert lightning_hold([29.4], [T_MAX + 60], 40)[0] is False      # released, not stuck
    assert lightning_hold([], [], 40)[0] is False

    # The parse, through the coordinator, from entities shaped exactly like Blitzortung's.
    Clock(STORM_NOW).install(monkeypatch)
    strikes = [State(f"geo_location.lightning_strike_{i}", distance, source="blitzortung", unit_of_measurement="km",
                     publication_date=published, external_id=f"strike{i}") for i, (distance, published) in enumerate(STORM)]
    home = Home(temp=28.0, ac=True, extra=strikes + [State("sensor.blitzortung", "unknown")])
    home.data["lightning_distance_sensor"] = ["sensor.blitzortung"]
    decision = home.cycle()
    snapshot = home.data_now["snapshot"]
    assert decision.blocked and home.state("climate.ac") == "off"
    assert snapshot.lightning_strikes == len(STORM) and abs(snapshot.lightning_closest - 29.4) < 0.1
    assert snapshot.invalid_entities == []                           # a resting marker sensor is not an error


def _slot(hour, minute, price):
    start = datetime(2026, 7, 4, hour, minute, tzinfo=CEST)
    return {"time_start": start.isoformat(), "time_end": (start + timedelta(minutes=15)).isoformat(), "SEK_per_kWh": price}


def test_prices_elpriset_and_nord_pool_shapes_rank_and_find_the_cheap_window():
    today = ([_slot(h, m, 0.11) for h in (12, 13, 14, 15) for m in (0, 15, 30, 45)] + [_slot(8, 45, 0.10)]
             + [_slot(h, m, 0.85) for h in (19, 20, 21, 22) for m in (0, 15, 30, 45)]
             + [_slot(18, 30, 0.39), _slot(18, 45, 0.51)])
    elpriset = {"today": today, "forecast": today}
    midday = datetime(2026, 7, 4, 13, 0, tzinfo=CEST)

    series = price_series(elpriset, midday)
    assert series and all(isinstance(value, float) for _, value in series)
    values = day_values(elpriset, midday)
    assert len(values) == len(today)
    assert price_rank(0.11, values) < 0.5 < 0.75 < price_rank(0.85, values)
    assert 12 <= cheapest_window(series, midday, duration_hours=2, horizon_hours=8).hour <= 15
    assert in_cheapest_window(series, midday, 2, 8) is True          # 15-minute slots, real hours

    midnight = datetime(2026, 7, 4, 0, 0, tzinfo=CEST)
    nord_pool = {"raw_today": [{"start": (midnight + timedelta(hours=h)).isoformat(), "value": 0.2} for h in range(24)]}
    assert price_series(nord_pool, midday)
    assert price_series({"today": [0.2] * 24}, midday)               # bare float list
    assert price_series({}, midday) == [] and day_values({}, midday) == []


def test_forecasts_local_wall_clock_times_do_not_drift_with_the_host_timezone(monkeypatch):
    # "15:00" with no offset means 15:00 on the comparison clock, whatever zone the host is in.
    naive = _normalize_datetime(datetime(2026, 9, 7, 15, 0), CEST)
    assert naive.hour == 15 and naive.astimezone(timezone.utc).hour == 13

    now = datetime(2026, 9, 7, 13, 0, tzinfo=CEST)
    weather = [{"datetime": f"2026-09-07T{hour:02d}:00", "temperature": temp}
               for hour, temp in [(13, 22), (14, 24), (15, 27), (16, 30), (17, 29)]]
    assert upcoming_peak(weather, now) == 30
    assert heat_outlook(weather, now, 22.0, "°C") > 0
    assert heat_outlook([{"datetime": "2026-09-07T14:00", "temperature": 20}], now, 22.0, "°C") == 0.0
    assert heat_outlook([{"datetime": "2026-09-07T14:00", "temperature": 95}], now, 22.0, "°F") > 0.3
    assert heat_outlook([], now, 22.0, "°C") == 0.0
    prices = [(now + timedelta(hours=i), price) for i, price in enumerate([0.05, 0.1, 0.3, 0.6, 0.7])]
    assert precool_opportunity(weather, prices, now, 22.0, "°C") > 0.8

    # Through the coordinator: Open-Meteo `hourly_forecast` and pollen `next_24_hours`, both
    # naive local strings. Only entries inside the next few hours count.
    Clock(now).install(monkeypatch)
    aqi = State("sensor.outdoor_aqi", 20, hourly_forecast=[
        {"datetime": "2026-09-07T12:00", "value": 300},              # already past
        {"datetime": "2026-09-07T15:00", "value": 140},              # soon
        {"datetime": "2026-09-08T09:00", "value": 400}])             # tomorrow
    pollen = State("sensor.pollen", 0.2, next_24_hours=[{"time": "2026-09-07T14:00", "value": 3.5}])
    home = Home(temp=21.0, ventilation=True, co2=900, extra=[aqi, pollen])
    home.data["outdoor_aqi_sensor"] = ["sensor.outdoor_aqi"]
    home.data["outdoor_pollen_sensor"] = ["sensor.pollen"]
    home.cycle()
    snapshot = home.data_now["snapshot"]
    assert snapshot.outdoor_aqi_soon == 140 and snapshot.outdoor_pollen_soon == 3.5
    assert home.state("fan.erv") == "on"                              # airing out before the bad air arrives


def test_units_psychrometrics_and_comfort_reference_values():
    assert abs(to_celsius(77.0, "°F") - 25.0) < 1e-9 and abs(to_celsius(295.15, "K") - 22.0) < 1e-9
    assert to_celsius(25.0, "°C") == 25.0 and to_celsius(25.0, None) == 25.0 and to_celsius(None, "°F") is None
    assert abs(from_celsius(to_celsius(71.6, "°F"), "°F") - 71.6) < 1e-9

    assert abs(dew_point(25.0, 60.0) - 16.7) < 0.1 and abs(dew_point(22.0, 40.0) - 7.8) < 0.1
    assert dew_point(None, 50) is None and dew_point(22.0, 0) is None

    # ISO 7730 PMV against the CBE Comfort Tool: (temp, rh, air speed, met, clo) -> PMV
    for temp, rh, speed, met, clo, expected in [
        (24, 39, 0.8, 1.1, 0.5, -1.686), (26, 45, 0.8, 1.1, 0.5, -0.752), (28, 45, 0.8, 1.1, 0.5, 0.147),
        (30, 42, 0.8, 1.1, 0.5, 1.023), (31, 45, 0.8, 1.1, 0.5, 1.510), (26, 45, 0.1, 1.1, 0.5, 0.159),
        (22, 50, 0.1, 1.1, 0.5, -1.125),
    ]:
        assert abs(pmv(temp, rh, speed, met, clo) - expected) < 0.01
    assert 4.9 < ppd(0.0) < 5.1 and ppd(1.0) > 20 and pmv(None, 45) is None

    # Damp air only ever takes whole degrees OFF the setpoint, by sensitivity.
    assert humidity_penalty(24.0, 40.0) == 0
    assert humidity_penalty(24.0, 60.0, "normal") == 1 and humidity_penalty(24.0, 85.0, "normal") == 2
    assert humidity_penalty(24.0, 60.0, "tolerant") == 0 and humidity_penalty(24.0, 55.0, "very_sensitive") >= 1
    assert humidity_penalty(24.0, None) == 0


def test_devices_feature_bitmasks_presets_speed_grids_and_time_formats():
    attrs = lambda **a: State("x.y", "on", **a)  # noqa: E731
    # Real devices: a 3-speed purifier (49), an on/off fan (48), a preset-only purifier (56).
    assert fan_features(attrs(supported_features=49)).set_speed and not fan_features(attrs(supported_features=49)).preset_mode
    assert not fan_features(attrs(supported_features=48)).set_speed
    assert fan_features(attrs(supported_features=56)).preset_mode and not fan_features(attrs(supported_features=56)).set_speed
    assert fan_features(attrs(percentage=50)).set_speed                      # no bitmask: inferred
    assert climate_features(attrs(supported_features=385)).target_temperature and climate_features(attrs(supported_features=385)).turn_off
    assert not climate_features(attrs(supported_features=128)).target_temperature
    assert climate_features(attrs()).target_temperature                      # missing bitmask: assume capable
    assert cover_features(attrs(supported_features=4)).set_position and not cover_features(attrs(supported_features=4)).open_close
    assert cover_features(attrs(supported_features=3)).open_close

    presets = ["Auto", "Silent", "Favorite", "Turbo"]
    assert [preset_for_speed(presets, tier) for tier in ("low", "medium", "high")] == ["Silent", "Favorite", "Turbo"]
    assert preset_for_speed(["Eco", "Custom"], "high") is None and preset_for_speed(None, "high") is None
    assert preset_fraction("Silent") < preset_fraction("Favorite") < preset_fraction("Turbo")

    assert [snap_percentage(p, 33.33) for p in (33, 66, 100)] == [33, 67, 100]
    assert snap_percentage(66, None) == 66 and snap_percentage(66, 0) == 66 and snap_percentage(10, 25) == 25

    # TimeSelector hands back a string, a dict, or a stringified dict depending on HA version.
    for value in ("22:00", "22:00:00", {"hour": 22, "minute": 0}, "{'hour': 22, 'minute': 0, 'second': 0}"):
        assert parse_time(value).hour == 22
    assert parse_time("nonsense") is None and parse_time(None) is None
    late, early, noon = parse_time("23:30"), parse_time("06:00"), parse_time("12:00")
    assert in_quiet_hours(late, "22:00", "07:00") and in_quiet_hours(early, "22:00", "07:00")
    assert not in_quiet_hours(noon, "22:00", "07:00") and not in_quiet_hours(noon, "22:00", "22:00")

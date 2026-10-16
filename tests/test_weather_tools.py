import pytest

from app.seed.seed import run_seed
from app.tools.weather_tools import (
    DISRUPTION_GUST_KMH, DISRUPTION_PRECIPITATION_MM, is_disruptive_day, query_weather_conditions, weather_risk_for,
)
from tests.weather_data import add_weather


def test_thresholds_are_the_documented_ones():
    assert DISRUPTION_PRECIPITATION_MM == 20 and DISRUPTION_GUST_KMH == 60


@pytest.mark.parametrize(
    "precipitation,gust,thunderstorm,expected",
    [
        (0, 10, False, False),
        (19.9, 59.9, False, False),
        (20, 10, False, True),
        (0, 60, False, True),
        (0, 10, True, True),
    ],
)
def test_is_disruptive_day(precipitation, gust, thunderstorm, expected):
    assert is_disruptive_day(precipitation, gust, thunderstorm) is expected


@pytest.mark.parametrize(
    "origin,destination,days,expected",
    [
        ("VFR", "VFR", 0, "LOW"),
        ("UNKNOWN", "UNKNOWN", 0, "LOW"),
        ("VFR", "MVFR", 0, "MODERATE"),
        ("MVFR", "VFR", 0, "MODERATE"),
        ("VFR", "VFR", 1, "MODERATE"),
        ("VFR", "VFR", 2, "MODERATE"),
        ("VFR", "VFR", 3, "HIGH"),
        ("VFR", "VFR", 7, "HIGH"),
        ("IFR", "VFR", 0, "HIGH"),
        ("VFR", "IFR", 0, "HIGH"),
        ("LIFR", "VFR", 0, "HIGH"),
        ("VFR", "LIFR", 1, "HIGH"),
        ("MVFR", "MVFR", 2, "MODERATE"),
    ],
)
def test_weather_risk_for(origin, destination, days, expected):
    assert weather_risk_for(origin, destination, days) == expected


async def test_without_weather_data_everything_is_unknown_and_low(db_session):
    await run_seed(db_session)

    result = await query_weather_conditions(db_session)

    weather = result["weather"]
    assert [a["airport"] for a in weather["airports"]] == ["BOM", "DEL", "BLR", "MAA", "HYD", "CCU"]
    assert all(a["flight_category"] == "UNKNOWN" and a["forecast_days"] == 0 for a in weather["airports"])
    routes = {r["route"]: r for r in weather["routes"]}
    assert set(routes) == {"BOM-DEL", "DEL-BOM", "BOM-BLR", "BLR-HYD", "MAA-CCU"}
    bom_del = routes["BOM-DEL"]
    assert bom_del["weather_risk"] == "LOW" and bom_del["disruption_days_next_7"] == 0
    assert bom_del["origin_flight_category"] == bom_del["destination_flight_category"] == "UNKNOWN"
    assert bom_del["forecast_days_available"] == 0


async def test_conditions_and_route_risk_from_stored_weather(db_session):
    await run_seed(db_session)
    await add_weather(
        db_session,
        observations={
            "BOM": dict(flight_category="IFR", visibility_sm=1.86, wind_kt=9.0),
            "DEL": "MVFR",
            "BLR": "VFR",
            "HYD": "VFR",
            "MAA": "VFR",
            "CCU": "VFR",
        },
        forecasts={
            # BOM: thunderstorm on day 1, heavy rain on day 3.   DEL: gusts on day 3 (same day) and day 5.
            "BOM": {1: (2.0, 30.0, 95), 3: (25.0, 40.0, 63)},
            "DEL": {3: (0.0, 62.0, 3), 5: (0.0, 60.0, 3)},
            "BLR": {2: (21.0, 10.0, 65)},
            "HYD": {},
            "MAA": {0: (1.0, 10.0, 96), 1: (1.0, 10.0, 99), 2: (30.0, 80.0, 95)},
            "CCU": {4: (0.0, 5.0, 1)},
        },
    )

    weather = (await query_weather_conditions(db_session))["weather"]

    airports = {a["airport"]: a for a in weather["airports"]}
    bom = airports["BOM"]
    assert bom["icao"] == "VABB" and bom["flight_category"] == "IFR" and bom["visibility_sm"] == 1.86
    assert bom["wind_kt"] == 9.0 and bom["observed_at"].startswith("2026-10-16T11:00")
    assert bom["forecast_days"] == 7 and bom["disruption_days"] == 2 and bom["thunderstorm_days"] == 1
    assert bom["max_precipitation_mm"] == 25.0 and bom["max_gust_kmh"] == 40.0
    assert bom["disruption_dates"] == ["2026-10-17", "2026-10-19"]
    assert airports["HYD"]["disruption_days"] == 0

    routes = {r["route"]: r for r in weather["routes"]}
    # IFR at the origin makes it HIGH regardless of the 3 disruption days.
    assert routes["BOM-DEL"]["weather_risk"] == "HIGH"
    assert routes["BOM-DEL"]["origin_flight_category"] == "IFR" and routes["BOM-DEL"]["destination_flight_category"] == "MVFR"
    # Union of days, not a sum: BOM 17 and 19, DEL 19 and 21 -> 3 distinct days.
    assert routes["BOM-DEL"]["disruption_days_next_7"] == 3
    assert routes["BOM-DEL"]["disruption_dates"] == ["2026-10-17", "2026-10-19", "2026-10-21"]
    assert routes["DEL-BOM"]["weather_risk"] == "HIGH"
    # BLR is VFR with one rainy day, HYD is quiet: MODERATE through the disruption day alone.
    assert routes["BLR-HYD"]["weather_risk"] == "MODERATE" and routes["BLR-HYD"]["disruption_days_next_7"] == 1
    # MAA has 3 thunderstorm/rain days, CCU none: HIGH through disruption days alone.
    assert routes["MAA-CCU"]["weather_risk"] == "HIGH" and routes["MAA-CCU"]["disruption_days_next_7"] == 3
    assert routes["BOM-BLR"]["weather_risk"] == "HIGH"  # BOM is IFR


async def test_mvfr_alone_is_moderate_and_a_clean_route_is_low(db_session):
    await run_seed(db_session)
    await add_weather(
        db_session,
        observations={"BLR": "MVFR", "HYD": "VFR", "MAA": "VFR", "CCU": "VFR"},
        forecasts={"BLR": {}, "HYD": {}, "MAA": {}, "CCU": {}},
    )

    routes = {r["route"]: r for r in (await query_weather_conditions(db_session))["weather"]["routes"]}

    assert routes["BLR-HYD"]["weather_risk"] == "MODERATE" and routes["BLR-HYD"]["disruption_days_next_7"] == 0
    assert routes["MAA-CCU"]["weather_risk"] == "LOW" and routes["MAA-CCU"]["disruption_days_next_7"] == 0
    assert routes["MAA-CCU"]["forecast_days_available"] == 7

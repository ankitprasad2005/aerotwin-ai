import pytest

from app.seed.seed import run_seed
from app.tools.weather_tools import query_weather_conditions, weather_risk_for
from tests.ad_taf_data import add_tafs
from tests.weather_data import add_weather


@pytest.mark.parametrize(
    "tafs,thunderstorm,expected",
    [
        ((), False, "LOW"),  # no TAF adds nothing
        ((None, None), False, "LOW"),
        (("VFR", "VFR"), False, "LOW"),
        (("MVFR", "MVFR"), False, "LOW"),  # MVFR forecast alone is not an extra risk
        (("IFR", "VFR"), False, "HIGH"),
        (("VFR", "IFR"), False, "HIGH"),
        (("LIFR", None), False, "HIGH"),
        (("VFR", "VFR"), True, "HIGH"),
        ((None, None), True, "HIGH"),
    ],
)
def test_taf_branches_of_weather_risk_for(tafs, thunderstorm, expected):
    assert weather_risk_for("VFR", "VFR", 0, tafs, thunderstorm) == expected


def test_existing_rules_are_unchanged_by_the_taf_arguments():
    assert weather_risk_for("VFR", "MVFR", 0, ("VFR", "VFR"), False) == "MODERATE"
    assert weather_risk_for("VFR", "VFR", 1, ("MVFR", None), False) == "MODERATE"
    assert weather_risk_for("IFR", "VFR", 0, ("VFR", "VFR"), False) == "HIGH"
    assert weather_risk_for("VFR", "VFR", 3, (), False) == "HIGH"
    assert weather_risk_for("VFR", "VFR", 0) == "LOW"


async def test_the_tool_reports_tafs_and_raises_the_route_risk(db_session):
    await run_seed(db_session)
    await add_weather(
        db_session,
        observations={a: "VFR" for a in ("BOM", "DEL", "BLR", "HYD", "MAA", "CCU")},
        forecasts={a: {} for a in ("BOM", "DEL", "BLR", "HYD", "MAA", "CCU")},
    )
    await add_tafs(
        db_session,
        {
            "BOM": ("IFR", False),  # BOM-DEL, DEL-BOM, BOM-BLR: HIGH through the origin/destination TAF category
            "DEL": ("VFR", False),
            "BLR": ("MVFR", False),  # BLR-HYD stays LOW: MVFR is no extra risk
            "MAA": ("VFR", True),  # MAA-CCU: HIGH through the thunderstorm at the origin
            # HYD, CCU: no TAF
        },
    )

    weather = (await query_weather_conditions(db_session))["weather"]

    airports = {a["airport"]: a for a in weather["airports"]}
    assert airports["BOM"]["taf_worst_flight_category_24h"] == "IFR" and airports["BOM"]["taf_thunderstorm_24h"] is False
    assert airports["MAA"]["taf_thunderstorm_24h"] is True
    assert airports["HYD"]["taf_worst_flight_category_24h"] is None and airports["HYD"]["taf_thunderstorm_24h"] is None
    routes = {r["route"]: r for r in weather["routes"]}
    assert routes["BOM-DEL"]["weather_risk"] == "HIGH" and routes["DEL-BOM"]["weather_risk"] == "HIGH"
    assert routes["BOM-DEL"]["origin_taf_worst_flight_category_24h"] == "IFR"
    assert routes["BOM-DEL"]["destination_taf_worst_flight_category_24h"] == "VFR"
    assert routes["BOM-DEL"]["taf_thunderstorm_24h"] is False
    assert routes["BOM-BLR"]["weather_risk"] == "HIGH"
    assert routes["BLR-HYD"]["weather_risk"] == "LOW"
    assert routes["BLR-HYD"]["destination_taf_worst_flight_category_24h"] is None and routes["BLR-HYD"]["taf_thunderstorm_24h"] is False
    assert routes["MAA-CCU"]["weather_risk"] == "HIGH" and routes["MAA-CCU"]["taf_thunderstorm_24h"] is True
    # The existing observation-based fields are untouched.
    assert routes["BOM-DEL"]["origin_flight_category"] == "VFR" and routes["BOM-DEL"]["disruption_days_next_7"] == 0


async def test_a_thunderstorm_at_the_destination_end_also_makes_the_route_high(db_session):
    await run_seed(db_session)
    await add_weather(
        db_session,
        observations={a: "VFR" for a in ("BLR", "HYD")},
        forecasts={a: {} for a in ("BLR", "HYD")},
    )
    await add_tafs(db_session, {"BLR": ("VFR", False), "HYD": ("VFR", True)})

    routes = {r["route"]: r for r in (await query_weather_conditions(db_session))["weather"]["routes"]}

    assert routes["BLR-HYD"]["weather_risk"] == "HIGH" and routes["BLR-HYD"]["taf_thunderstorm_24h"] is True


async def test_without_any_taf_the_route_fields_are_null_and_risk_is_as_before(db_session):
    await run_seed(db_session)

    routes = {r["route"]: r for r in (await query_weather_conditions(db_session))["weather"]["routes"]}

    assert routes["BOM-DEL"]["taf_thunderstorm_24h"] is None
    assert routes["BOM-DEL"]["origin_taf_worst_flight_category_24h"] is None
    assert routes["BOM-DEL"]["weather_risk"] == "LOW"

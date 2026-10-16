from datetime import date

import pytest

from app.models.external import MarketRoute, WorldBankIndicator
from app.seed.seed import run_seed
from app.tools import market_tools
from app.tools.market_tools import competition_level_for, demand_outlook_for, query_market_conditions


@pytest.mark.parametrize("rivals,level", [(0, "LOW"), (1, "LOW"), (2, "LOW"), (3, "MODERATE"), (4, "MODERATE"), (5, "HIGH"), (9, "HIGH")])
def test_competition_level_thresholds(rivals, level):
    assert competition_level_for(rivals) == level


@pytest.mark.parametrize(
    "growth,holidays,load_factor,expected",
    [
        (5.0, 0, 0.75, "STRONG"),        # growth exactly at the threshold, load factor exactly at the threshold
        (6.0, 0, 0.9, "STRONG"),
        (None, 2, 0.75, "STRONG"),       # holidays alone (two) are enough
        (-1.0, 2, 0.8, "STRONG"),        # STRONG is tested before WEAK
        (4.99, 1, 0.9, "STABLE"),        # neither growth nor holidays reach their thresholds
        (9.0, 3, 0.74, "STABLE"),        # demand signal but load factor below 0.75
        (9.0, 3, 0.59, "WEAK"),          # load factor below 0.6 is WEAK even with strong growth
        (9.0, 3, 0.6, "STABLE"),         # exactly 0.6 is not weak
        (-0.1, 0, 0.9, "WEAK"),          # negative passenger growth
        (0.0, 0, 0.9, "STABLE"),         # zero growth is not negative
        (None, 0, 0.5, "WEAK"),
        (None, 1, None, "STABLE"),       # missing inputs never produce STRONG or WEAK
        (8.0, 4, None, "STABLE"),        # STRONG needs a known load factor
        (-3.0, 0, None, "WEAK"),
    ],
)
def test_demand_outlook_branches(growth, holidays, load_factor, expected):
    assert demand_outlook_for(growth, holidays, load_factor) == expected


def _market(origin, destination, *codes):
    return [MarketRoute(airline_code=c, airline_name=c, origin=origin, destination=destination) for c in codes]


async def _seed_market(db):
    await run_seed(db)
    db.add_all([
        # BOM-DEL: 6E, AI, SG across both directions, with a duplicate 6E row -> 3 distinct rivals (MODERATE).
        *_market("BOM", "DEL", "6E", "AI", "6E"), *_market("DEL", "BOM", "SG", "6E"),
        # BOM-BLR: five distinct airlines -> HIGH.
        *_market("BOM", "BLR", "6E", "AI", "SG", "UK", "G8"),
        # BLR-HYD: one airline -> LOW. MAA-CCU and DEL-BOM(from the reverse rows above) as given.
        *_market("BLR", "HYD", "6E"),
    ])
    await db.flush()


def _fix_today(monkeypatch, day):
    monkeypatch.setattr(market_tools, "_today", lambda: day)


async def test_tool_reports_competition_national_context_and_outlook(db_session, monkeypatch):
    _fix_today(monkeypatch, date(2026, 10, 16))
    await _seed_market(db_session)
    db_session.add_all([
        WorldBankIndicator(indicator="IS.AIR.PSGR", year=2022, value=100.0),
        WorldBankIndicator(indicator="IS.AIR.PSGR", year=2023, value=110.0),
        WorldBankIndicator(indicator="NY.GDP.MKTP.KD.ZG", year=2025, value=7.5),
    ])
    await db_session.flush()

    market = (await query_market_conditions(db_session))["market"]

    assert market["national"] == {
        "passenger_growth_pct": 10.0, "passenger_data_year": 2023, "gdp_growth_pct": 7.5,
        "holidays_next_8_weeks": 3, "holiday_window_weeks": 8,
        "holidays": [
            {"date": "2026-10-20", "name": "Dussehra"},
            {"date": "2026-11-08", "name": "Diwali (Deepavali)"},
            {"date": "2026-11-24", "name": "Guru Nanak's Jayanti"},
        ],
    }
    assert market["notes"] == []
    by_route = {r["route"]: r for r in market["routes"]}
    assert [r["route"] for r in market["routes"]] == sorted(by_route, key=lambda k: tuple(k.split("-")))
    assert by_route["BOM-DEL"] == {
        "route": "BOM-DEL", "rival_airlines": 3, "competition_level": "MODERATE",
        "historical_load_factor": 0.81, "demand_outlook": "STRONG",
    }
    assert by_route["DEL-BOM"]["rival_airlines"] == 3  # either direction counts
    assert (by_route["BOM-BLR"]["rival_airlines"], by_route["BOM-BLR"]["competition_level"]) == (5, "HIGH")
    assert by_route["BOM-BLR"]["demand_outlook"] == "STABLE"  # growth and holidays strong, load factor 0.68 < 0.75
    assert (by_route["BLR-HYD"]["rival_airlines"], by_route["BLR-HYD"]["competition_level"]) == (1, "LOW")
    assert by_route["BLR-HYD"]["demand_outlook"] == "WEAK"  # load factor 0.55
    assert (by_route["MAA-CCU"]["rival_airlines"], by_route["MAA-CCU"]["competition_level"]) == (0, "LOW")
    assert by_route["MAA-CCU"]["demand_outlook"] == "STABLE"


async def test_negative_passenger_growth_makes_a_mediocre_route_weak(db_session, monkeypatch):
    _fix_today(monkeypatch, date(2026, 6, 30))  # only Independence Day falls in the window
    await _seed_market(db_session)
    db_session.add_all([
        WorldBankIndicator(indicator="IS.AIR.PSGR", year=2022, value=100.0),
        WorldBankIndicator(indicator="IS.AIR.PSGR", year=2023, value=90.0),
    ])
    await db_session.flush()

    market = (await query_market_conditions(db_session))["market"]

    assert market["national"]["passenger_growth_pct"] == -10.0 and market["national"]["holidays_next_8_weeks"] == 1
    assert market["national"]["gdp_growth_pct"] is None
    assert "No World Bank GDP growth data." in market["notes"]
    assert {r["demand_outlook"] for r in market["routes"]} == {"WEAK"}


async def test_missing_data_gives_nulls_and_notes_never_invented_values(db_session, monkeypatch):
    _fix_today(monkeypatch, date(2026, 6, 30))
    await run_seed(db_session)

    market = (await query_market_conditions(db_session))["market"]

    assert market["national"]["passenger_growth_pct"] is None and market["national"]["gdp_growth_pct"] is None
    assert market["national"]["passenger_data_year"] is None
    assert len(market["notes"]) == 3
    assert any("passenger" in n for n in market["notes"]) and any("OpenFlights" in n for n in market["notes"])
    for route in market["routes"]:
        assert route["rival_airlines"] is None and route["competition_level"] is None
    by_route = {r["route"]: r for r in market["routes"]}
    assert by_route["BOM-DEL"]["demand_outlook"] == "STABLE"  # no growth data, one holiday, load factor 0.81
    assert by_route["BLR-HYD"]["demand_outlook"] == "WEAK"  # the load factor alone is enough


async def test_missing_previous_year_is_noted(db_session, monkeypatch):
    _fix_today(monkeypatch, date(2026, 6, 30))
    await run_seed(db_session)
    db_session.add(WorldBankIndicator(indicator="IS.AIR.PSGR", year=2023, value=110.0))
    await db_session.flush()

    market = (await query_market_conditions(db_session))["market"]

    assert market["national"]["passenger_growth_pct"] is None and market["national"]["passenger_data_year"] == 2023
    assert any("2022" in n and "missing" in n for n in market["notes"])


async def test_route_without_demand_row_has_null_load_factor(db_session, monkeypatch):
    from sqlalchemy import delete

    from app.models.digital_twin import PassengerDemand

    _fix_today(monkeypatch, date(2026, 6, 30))
    await run_seed(db_session)
    await db_session.execute(delete(PassengerDemand))
    await db_session.flush()

    market = (await query_market_conditions(db_session))["market"]

    assert all(r["historical_load_factor"] is None and r["demand_outlook"] == "STABLE" for r in market["routes"])

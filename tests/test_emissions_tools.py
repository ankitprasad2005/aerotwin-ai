import pytest

from app.models.digital_twin import Airport, Route
from app.seed.seed import run_seed
from app.tools.emissions_tools import (
    CO2_KG_PER_KG_FUEL,
    EMISSIONS_METHODOLOGY_SOURCES,
    KM_PER_NAUTICAL_MILE,
    PER_PASSENGER_STANCE_THRESHOLD,
    A320_FUEL_KG_BY_DISTANCE_NM,
    emissions_change_impact,
    emissions_stance,
    flown_distance_km,
    fuel_kg_for_distance_nm,
    query_route_emissions,
)


def test_constants_match_the_icao_methodology():
    assert CO2_KG_PER_KG_FUEL == 3.16
    assert KM_PER_NAUTICAL_MILE == 1.852
    assert PER_PASSENGER_STANCE_THRESHOLD == 0.02
    assert A320_FUEL_KG_BY_DISTANCE_NM == (
        (125, 1672), (250, 3430), (500, 4585), (750, 6212), (1000, 7772), (1500, 10766), (2000, 13648), (2500, 16452),
    )


def test_methodology_sources_name_the_icao_document_and_the_table():
    text = " ".join(EMISSIONS_METHODOLOGY_SOURCES)
    assert "ICAO Carbon Emissions Calculator Methodology" in text
    assert "Version 13.1" in text and "Appendix C" in text and "3.16" in text


@pytest.mark.parametrize(
    "gcd_km, expected",
    [(100, 150), (549.9, 599.9), (550, 650), (1150, 1250), (5500, 5600), (5500.1, 5625.1)],
)
def test_flown_distance_adds_the_icao_gcd_correction(gcd_km, expected):
    assert flown_distance_km(gcd_km) == pytest.approx(expected)


@pytest.mark.parametrize(
    "nm, expected",
    [
        (125, 1672.0),  # a table band is returned exactly
        (500, 4585.0),
        (2500, 16452.0),
        (625, 5398.5),  # halfway between 500 (4585) and 750 (6212)
        (62.5, 836.0),  # below the first band: proportional to distance, 1672 x 62.5 / 125
        (0, 0.0),
        (3000, 19256.0),  # beyond the last band: last segment continued, 16452 + (16452-13648)/500 x 500
    ],
)
def test_fuel_interpolates_linearly_between_bands(nm, expected):
    assert fuel_kg_for_distance_nm(nm) == pytest.approx(expected)


def test_fuel_for_the_bom_del_flown_distance():
    # 1150 km + 100 km = 1250 km = 674.946 nm; 4585 + (674.946 - 500) / 250 x (6212 - 4585) = 5723.5486 kg
    assert fuel_kg_for_distance_nm(flown_distance_km(1150) / KM_PER_NAUTICAL_MILE) == pytest.approx(5723.5486, abs=1e-3)


def _impact(**overrides):
    inputs = dict(
        current_frequency=7, seats_per_flight=180, historical_load_factor=0.81, projected_load_factor=0.9,
        co2_kg_per_flight=18000.0, change=1,
    )
    inputs.update(overrides)
    return emissions_change_impact(**inputs)


def test_increase_impact_exact_numbers():
    # Before: 7 x 18000 = 126 t over 7 x 180 x 0.81 = 1020.6 passengers -> 18000 / 145.8 = 123.45679 kg each.
    # After: 8 x 18000 = 144 t over 8 x 180 x 0.9 = 1296 passengers -> 18000 / 162 = 111.11111 kg each (-10%).
    assert _impact() == {
        "new_weekly_co2_tonnes": 144.0,
        "co2_change_tonnes_per_week": 18.0,
        "co2_per_passenger_kg_before": 123.46,
        "co2_per_passenger_kg_after": 111.11,
        "emissions_stance": "SUPPORTS",
    }


def test_decrease_impact_exact_numbers():
    # 6 flights = 108 t (-18 t); 6 x 180 x 0.9 = 972 passengers -> 18000 / 162 = 111.11 kg each.
    result = _impact(change=-1)
    assert result["new_weekly_co2_tonnes"] == 108.0
    assert result["co2_change_tonnes_per_week"] == -18.0
    assert result["co2_per_passenger_kg_after"] == 111.11
    assert result["emissions_stance"] == "SUPPORTS"  # total weekly CO2 falls


def test_change_that_removes_every_flight_is_not_a_frequency_change():
    assert _impact(current_frequency=1, change=-1) is None
    assert _impact(current_frequency=0, change=-1) is None


def test_route_with_no_passengers_today_reports_zero_per_passenger_before():
    result = _impact(current_frequency=0, change=1)
    assert result["co2_per_passenger_kg_before"] == 0.0
    assert result["co2_per_passenger_kg_after"] == 111.11
    assert result["emissions_stance"] == "NEUTRAL"  # total rises and there is nothing to compare per passenger


@pytest.mark.parametrize(
    "before, after, total_change, expected",
    [
        (100.0, 97.9, 5.0, "SUPPORTS"),  # per passenger falls by 2.1% (> 2%)
        (100.0, 98.0, 5.0, "NEUTRAL"),  # falls by exactly 2%: not more than 2%
        (100.0, 100.0, 5.0, "NEUTRAL"),
        (100.0, 102.0, 5.0, "NEUTRAL"),  # rises by exactly 2%
        (100.0, 102.1, 5.0, "OPPOSES"),  # rises by 2.1% (> 2%) and total rises
        (100.0, 102.1, 0.0, "OPPOSES"),  # total unchanged does not count as falling
        (100.0, 150.0, -3.0, "SUPPORTS"),  # total weekly CO2 falls: SUPPORTS wins over a per-passenger rise
        (100.0, 100.0, -0.001, "SUPPORTS"),
        (0.0, 50.0, 5.0, "NEUTRAL"),  # no passengers before: nothing to compare
        (100.0, 0.0, 5.0, "NEUTRAL"),  # no passengers after: nothing to compare
    ],
)
def test_emissions_stance_branches(before, after, total_change, expected):
    assert emissions_stance(before, after, total_change) == expected


# ---------------------------------------------------------------------------- the tool


async def test_query_route_emissions_empty_db_returns_empty_list(db_session):
    assert await query_route_emissions(db_session) == {"emissions": []}


async def test_query_route_emissions_bom_del_with_seed_numbers(db_session):
    await run_seed(db_session)

    routes = {r["route"]: r for r in (await query_route_emissions(db_session))["emissions"]}

    bom_del = routes["BOM-DEL"]
    assert set(routes) == {"BOM-DEL", "DEL-BOM", "BOM-BLR", "BLR-HYD", "MAA-CCU"}
    assert bom_del["current_frequency"] == 7
    assert bom_del["distance_km"] == 1150
    assert bom_del["flown_distance_km"] == 1250
    assert bom_del["aircraft_type"] == "A320"
    assert bom_del["fuel_kg_per_flight"] == 5723.5
    # 5723.5486 kg x 3.16 = 18086.4 kg of CO2 per flight; 7 flights = 126.604 t a week.
    assert bom_del["co2_kg_per_flight"] == 18086.4
    assert bom_del["current_weekly_co2_tonnes"] == 126.605
    assert bom_del["co2_per_passenger_kg_current"] == 124.05  # 18086.4136 / (180 x 0.81)
    assert bom_del["methodology_sources"] == list(EMISSIONS_METHODOLOGY_SOURCES)

    increase = bom_del["impact_if_increase_by_one_weekly_flight"]
    # 8 flights = 144.691 t (+18.086 t); projected load factor 0.9 -> 1296 passengers -> 18086.4136 / 162 = 111.64 kg.
    assert increase == {
        "fuel_kg_per_flight": 5723.5,
        "co2_kg_per_flight": 18086.4,
        "new_weekly_co2_tonnes": 144.691,
        "co2_change_tonnes_per_week": 18.086,
        "co2_per_passenger_kg_before": 124.05,
        "co2_per_passenger_kg_after": 111.64,
        "emissions_stance": "SUPPORTS",  # 124.05 -> 111.64 is a 10.0% fall
    }
    decrease = bom_del["impact_if_decrease_by_one_weekly_flight"]
    # 6 flights = 108.518 t (-18.086 t); projected load factor 0.9 -> 972 passengers -> 18086.4136 / 162 = 111.64 kg.
    assert decrease["co2_change_tonnes_per_week"] == -18.086
    assert decrease["new_weekly_co2_tonnes"] == 108.518
    assert decrease["co2_per_passenger_kg_after"] == 111.64
    assert decrease["emissions_stance"] == "SUPPORTS"


async def test_query_route_emissions_uses_the_short_haul_distance_correction(db_session):
    await run_seed(db_session)

    blr_hyd = {r["route"]: r for r in (await query_route_emissions(db_session))["emissions"]}["BLR-HYD"]

    assert blr_hyd["flown_distance_km"] == 550  # 500 km < 550 km: +50 km
    assert blr_hyd["fuel_kg_per_flight"] == 3647.0
    assert blr_hyd["co2_kg_per_flight"] == 11524.6


async def test_query_route_emissions_route_without_load_data_has_no_impacts(db_session):
    origin = Airport(code="XYZ", name="Test Origin", city="Testville", country="Testland")
    destination = Airport(code="ABC", name="Test Dest", city="Testburg", country="Testland")
    db_session.add_all([origin, destination])
    await db_session.flush()
    db_session.add(Route(origin_id=origin.id, destination_id=destination.id, distance_km=500, current_frequency=1))
    await db_session.flush()

    (entry,) = (await query_route_emissions(db_session))["emissions"]

    assert entry["route"] == "XYZ-ABC"
    assert entry["co2_kg_per_flight"] == 11524.6
    assert entry["current_weekly_co2_tonnes"] == 11.525
    assert entry["co2_per_passenger_kg_current"] is None
    assert entry["impact_if_increase_by_one_weekly_flight"] is None
    assert entry["impact_if_decrease_by_one_weekly_flight"] is None

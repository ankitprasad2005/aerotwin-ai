import pytest
from sqlalchemy import delete, select

from app.models.digital_twin import PassengerDemand, Route
from app.seed.seed import run_seed
from app.tools import pricing_tools
from app.tools.digital_twin_tools import MAX_LOAD_FACTOR
from app.tools.pricing_tools import (
    ELASTICITY_SOURCES,
    FARE_CUT_OPPOSES_PCT,
    FARE_TEST_PCT,
    INTRA_ASIA_MULTIPLIER,
    NATIONAL_ELASTICITY,
    PAN_NATIONAL_ELASTICITY,
    ROUTE_ELASTICITY,
    ROUTE_ELASTICITY_USED,
    SHORT_HAUL_MULTIPLIER,
    fare_change_to_fill_pct,
    pricing_stance,
    query_pricing_options,
    revenue_change_if_fare_moves,
)


def test_constants_match_the_intervistas_report():
    # InterVISTAS 2007, Executive Summary pp. iii-v: base route -1.4, national -0.8, pan-national -0.6,
    # Intra Asia 0.95, short haul 1.1; worked example 3 (p. v) gives -1.4 x 0.95 x 1.1 = -1.46.
    assert (ROUTE_ELASTICITY, NATIONAL_ELASTICITY, PAN_NATIONAL_ELASTICITY) == (-1.4, -0.8, -0.6)
    assert (INTRA_ASIA_MULTIPLIER, SHORT_HAUL_MULTIPLIER) == (0.95, 1.1)
    assert ROUTE_ELASTICITY_USED == -1.463
    assert round(ROUTE_ELASTICITY_USED, 2) == -1.46
    assert (FARE_TEST_PCT, FARE_CUT_OPPOSES_PCT) == (5.0, 10.0)


def test_sources_cite_the_document_year_section_and_url():
    text = " ".join(ELASTICITY_SOURCES)
    for needle in ("InterVISTAS", "Estimating Air Travel Demand Elasticities", "2007", "Executive Summary", "iata.org"):
        assert needle in text


def test_fare_change_with_unit_elasticity_is_the_inverse_of_the_demand_ratio():
    # Q2 = Q1 x (P2/P1)^e. Demand 100, target 200, e = -1: P2/P1 = 100/200 = 0.5, a 50% cut.
    assert fare_change_to_fill_pct(weekly_demand=100, target_passengers=200, elasticity=-1.0) == pytest.approx(-50.0)


def test_fare_change_with_elasticity_two():
    # e = -2: P2/P1 = (200/100)^(1/-2) = 0.70710678, a 29.2893% cut.
    assert fare_change_to_fill_pct(weekly_demand=100, target_passengers=200, elasticity=-2.0) == pytest.approx(-29.2893, abs=1e-4)


def test_fare_change_is_none_when_demand_already_fills_the_target():
    assert fare_change_to_fill_pct(weekly_demand=200, target_passengers=200, elasticity=-1.4) is None
    assert fare_change_to_fill_pct(weekly_demand=300, target_passengers=200, elasticity=-1.4) is None


def test_revenue_change_for_a_five_percent_cut_with_elastic_demand():
    # fare 10, demand 100, e = -2, ceiling 200. Base 10 x 100 = 1000.
    # Cut: Q = 100 / 0.95^2 = 110.8033, revenue 9.5 x 110.8033 = 1052.6316 -> +52.6316.
    assert revenue_change_if_fare_moves(
        fare=10.0, weekly_demand=100, ceiling=200, elasticity=-2.0, fare_change_pct=-5.0
    ) == pytest.approx(52.6316, abs=1e-4)


def test_revenue_change_for_a_five_percent_rise_with_elastic_demand():
    # Rise: Q = 100 / 1.05^2 = 90.7029, revenue 10.5 x 90.7029 = 952.3810 -> -47.6190.
    assert revenue_change_if_fare_moves(
        fare=10.0, weekly_demand=100, ceiling=200, elasticity=-2.0, fare_change_pct=5.0
    ) == pytest.approx(-47.6190, abs=1e-4)


def test_revenue_change_is_capped_by_capacity():
    # Ceiling 105: the cut would draw 110.8 passengers but only 105 fit: 9.5 x 105 = 997.5 vs 1000 -> -2.5.
    assert revenue_change_if_fare_moves(
        fare=10.0, weekly_demand=100, ceiling=105, elasticity=-2.0, fare_change_pct=-5.0
    ) == pytest.approx(-2.5)


def test_revenue_change_when_capacity_binds_both_before_and_after():
    # Demand 150 > ceiling 100: base 10 x 100 = 1000; a rise to 10.5 still leaves demand 136 > 100, so 1050 -> +50.
    assert revenue_change_if_fare_moves(
        fare=10.0, weekly_demand=150, ceiling=100, elasticity=-2.0, fare_change_pct=5.0
    ) == pytest.approx(50.0)


@pytest.mark.parametrize(
    "is_increase, fare_change, plus5, expected",
    [
        (True, None, -10.0, "SUPPORTS"),   # demand already fills the new seats
        (True, -10.0, 0.0, "NEUTRAL"),     # exactly 10% is not deeper than 10%
        (True, -4.0, 0.0, "NEUTRAL"),
        (True, -10.01, 0.0, "OPPOSES"),
        (False, None, 12.0, "SUPPORTS"),   # decrease and a 5% rise raises revenue
        (False, None, 0.0, "NEUTRAL"),
        (False, None, -3.0, "NEUTRAL"),
    ],
)
def test_pricing_stance_thresholds(is_increase, fare_change, plus5, expected):
    assert pricing_stance(is_increase=is_increase, fare_change_pct=fare_change, revenue_plus_5pct=plus5) == expected


async def test_query_pricing_options_for_the_seed(db_session):
    await run_seed(db_session)
    result = await query_pricing_options(db_session)
    by_route = {r["route"]: r for r in result["pricing"]}
    assert set(by_route) == {"BOM-DEL", "DEL-BOM", "BOM-BLR", "BLR-HYD", "MAA-CCU"}
    assert result["elasticity_sources"] == list(ELASTICITY_SOURCES)

    # DEL-BOM: weekly demand 17500/13 = 1346.15; 8 flights x 180 x 0.9 = 1296 seats fit: demand fills them, no cut.
    del_bom = by_route["DEL-BOM"]
    assert del_bom["elasticity_used"] == -1.463
    assert del_bom["elasticity_sources"] == list(ELASTICITY_SOURCES)
    up = del_bom["impact_if_increase_by_one_weekly_flight"]
    assert up["fare_change_to_fill_added_seats_pct"] is None
    assert up["pricing_stance"] == "SUPPORTS"
    # Fare 95, demand 1346.1538, ceiling 1296. Base 95 x 1296 = 123120. -5%: fare 90.25 x 1296.
    assert up["revenue_change_if_fare_minus_5pct_usd"] == pytest.approx(90.25 * 1296 - 123120, abs=0.01)
    q_plus = 17500 / 13 * 1.05 ** -1.463
    assert up["revenue_change_if_fare_plus_5pct_usd"] == pytest.approx(99.75 * min(q_plus, 1296) - 123120, abs=0.01)

    # BLR-HYD: weekly demand 4100/13 = 315.3846; 4 x 180 x 0.9 = 648 to fill.
    blr_hyd = by_route["BLR-HYD"]["impact_if_increase_by_one_weekly_flight"]
    ratio = (648 / (4100 / 13)) ** (1 / -1.463)
    assert blr_hyd["fare_change_to_fill_added_seats_pct"] == pytest.approx((ratio - 1) * 100, abs=0.01)
    assert blr_hyd["fare_change_to_fill_added_seats_pct"] < -10
    assert blr_hyd["pricing_stance"] == "OPPOSES"
    assert blr_hyd["new_weekly_capacity_seats"] == 720

    down = by_route["DEL-BOM"]["impact_if_decrease_by_one_weekly_flight"]
    assert down["fare_change_to_fill_added_seats_pct"] is None
    assert down["new_weekly_capacity_seats"] == 7 * 180 - 180


async def test_query_pricing_options_has_no_decrease_for_a_single_flight_route(db_session):
    await run_seed(db_session)
    for route in (await db_session.execute(select(Route))).scalars():
        route.current_frequency = 1
    await db_session.flush()
    result = await query_pricing_options(db_session)
    assert all(r["impact_if_decrease_by_one_weekly_flight"] is None for r in result["pricing"])
    assert all(r["impact_if_increase_by_one_weekly_flight"] is not None for r in result["pricing"])


async def test_query_pricing_options_without_demand_has_no_impacts(db_session):
    await run_seed(db_session)
    await db_session.execute(delete(PassengerDemand))
    result = await query_pricing_options(db_session)
    assert all(r["impact_if_increase_by_one_weekly_flight"] is None for r in result["pricing"])
    assert all(r["impact_if_decrease_by_one_weekly_flight"] is None for r in result["pricing"])
    assert all(r["elasticity_used"] == -1.463 for r in result["pricing"])


def test_max_load_factor_is_shared_with_the_route_economics():
    assert pricing_tools.MAX_LOAD_FACTOR is MAX_LOAD_FACTOR

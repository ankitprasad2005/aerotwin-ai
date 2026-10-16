"""Fare moves implied by a one-flight weekly frequency change, from published air-travel price elasticities."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.digital_twin_tools import MAX_LOAD_FACTOR, WEEKS_PER_QUARTER, query_route_profitability

# Source of every elasticity below:
#   InterVISTAS Consulting Inc. for IATA, "Estimating Air Travel Demand Elasticities", Final Report,
#   28 December 2007, Executive Summary pp. iii-v ("Base Elasticities", "Geographic Aviation Market",
#   "Short-Haul/Long-Haul Adjustment", "Application of Adjustors"),
#   https://www.iata.org/en/iata-repository/publications/economic-reports/estimating-air-travel-demand-elasticities---by-intervistas
# Base elasticities by level of aggregation: route/market -1.4, national -0.8, pan-national -0.6.
ROUTE_ELASTICITY = -1.4
NATIONAL_ELASTICITY = -0.8
PAN_NATIONAL_ELASTICITY = -0.6
# Geographic market multiplier "Intra Asia 0.95" (the table has no India-specific row) and the
# "Short haul: 1.1 (+10%)" adjustor. Worked example 3 (p. v) multiplies them exactly this way:
# -1.4 x 0.95 x 1.1 = -1.46 (the report's table "Intra Asia, route/market, short-haul" also gives -1.46).
INTRA_ASIA_MULTIPLIER = 0.95
SHORT_HAUL_MULTIPLIER = 1.1
# A single airline fare change on one route is a ROUTE-level change (p. iii: "the route elasticity is
# applicable to a situation where the price of an individual route changes"). Rounded to 4 places to
# remove float noise (1.4 x 0.95 x 1.1 = 1.463).
ROUTE_ELASTICITY_USED = round(ROUTE_ELASTICITY * INTRA_ASIA_MULTIPLIER * SHORT_HAUL_MULTIPLIER, 4)

# Not from the report: the size of the fare test (+/-5%) and the depth of fare cut (10%) beyond which
# filling the added seats counts against the change.
FARE_TEST_PCT = 5.0
FARE_CUT_OPPOSES_PCT = 10.0

ELASTICITY_SOURCES = (
    "InterVISTAS Consulting Inc. for IATA, 'Estimating Air Travel Demand Elasticities', Final Report, 28 December 2007, "
    "https://www.iata.org/en/iata-repository/publications/economic-reports/estimating-air-travel-demand-elasticities---by-intervistas",
    "Base route/market elasticity -1.4 (national -0.8, pan-national -0.6), Executive Summary, 'Base Elasticities'.",
    "Elasticity used = -1.4 x 0.95 (Intra Asia market multiplier) x 1.1 (short-haul adjustor) = -1.463, "
    "Executive Summary, 'Application of Adjustors' example 3.",
)


def fare_change_to_fill_pct(*, weekly_demand: float, target_passengers: float, elasticity: float) -> float | None:
    """Fare change (percent, negative = cut) at which demand Q2 = Q1 x (P2/P1)^e equals `target_passengers`.

    Q1 is `weekly_demand` at today's fare. None when demand already reaches the target (no cut needed).
    """
    if weekly_demand >= target_passengers:
        return None
    return ((target_passengers / weekly_demand) ** (1 / elasticity) - 1) * 100


def revenue_change_if_fare_moves(
    *, fare: float, weekly_demand: float, ceiling: float, elasticity: float, fare_change_pct: float
) -> float:
    """Weekly revenue change (USD) when the fare moves by `fare_change_pct`; passengers = min(demand, ceiling)."""
    new_fare = fare * (1 + fare_change_pct / 100)
    new_demand = weekly_demand * (new_fare / fare) ** elasticity
    return new_fare * min(new_demand, ceiling) - fare * min(weekly_demand, ceiling)


def pricing_stance(*, is_increase: bool, fare_change_pct: float | None, revenue_plus_5pct: float) -> str:
    """SUPPORTS, NEUTRAL or OPPOSES.

    Increase: SUPPORTS when no fare cut is needed (None); OPPOSES when the cut is deeper than
    FARE_CUT_OPPOSES_PCT; NEUTRAL otherwise. Decrease: SUPPORTS when a FARE_TEST_PCT fare rise raises
    revenue, else NEUTRAL.
    """
    if is_increase:
        if fare_change_pct is None:
            return "SUPPORTS"
        return "OPPOSES" if fare_change_pct < -FARE_CUT_OPPOSES_PCT else "NEUTRAL"
    return "SUPPORTS" if revenue_plus_5pct > 0 else "NEUTRAL"


def _impact(*, route: dict, change: int) -> dict | None:
    new_frequency = route["current_frequency"] + change
    if new_frequency <= 0:
        return None
    fare = route["average_fare_usd"]
    weekly_demand = route["demand"] / WEEKS_PER_QUARTER
    capacity = new_frequency * route["seats_per_flight"]
    ceiling = capacity * MAX_LOAD_FACTOR
    is_increase = change > 0
    elasticity = ROUTE_ELASTICITY_USED
    fare_change = (
        fare_change_to_fill_pct(weekly_demand=weekly_demand, target_passengers=ceiling, elasticity=elasticity)
        if is_increase
        else None
    )
    moves = {
        pct: revenue_change_if_fare_moves(
            fare=fare, weekly_demand=weekly_demand, ceiling=ceiling, elasticity=elasticity, fare_change_pct=pct
        )
        for pct in (-FARE_TEST_PCT, FARE_TEST_PCT)
    }
    return {
        "new_weekly_capacity_seats": capacity,
        "weekly_passengers_filled_at_max_load_factor": round(ceiling, 2),
        "fare_change_to_fill_added_seats_pct": round(fare_change, 2) if fare_change is not None else None,
        "revenue_change_if_fare_minus_5pct_usd": round(moves[-FARE_TEST_PCT], 2),
        "revenue_change_if_fare_plus_5pct_usd": round(moves[FARE_TEST_PCT], 2),
        "pricing_stance": pricing_stance(
            is_increase=is_increase, fare_change_pct=fare_change, revenue_plus_5pct=moves[FARE_TEST_PCT]
        ),
    }


async def query_pricing_options(db: AsyncSession) -> dict:
    """For every route and both actions: the fare move needed to fill the added seats and the +/-5% revenue effect.

    Demand, fares, seats and frequencies come from query_route_profitability so they match what the network
    agent saw. Every figure is precomputed here, never left to the LLM.
    """
    results = []
    for route in (await query_route_profitability(db))["routes"]:
        complete = None not in (route["demand"], route["seats_per_flight"], route["average_fare_usd"])
        weekly_demand = route["demand"] / WEEKS_PER_QUARTER if route["demand"] is not None else None
        results.append(
            {
                "route": route["route"],
                "current_frequency": route["current_frequency"],
                "average_fare_usd": route["average_fare_usd"],
                "seats_per_flight": route["seats_per_flight"],
                "weekly_demand_passengers": round(weekly_demand, 2) if weekly_demand is not None else None,
                "elasticity_used": ROUTE_ELASTICITY_USED,
                "elasticity_sources": list(ELASTICITY_SOURCES),
                "impact_if_increase_by_one_weekly_flight": _impact(route=route, change=1) if complete else None,
                "impact_if_decrease_by_one_weekly_flight": _impact(route=route, change=-1) if complete else None,
            }
        )
    return {"pricing": results, "elasticity_sources": list(ELASTICITY_SOURCES)}

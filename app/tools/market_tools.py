from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import world_bank
from app.datasets.india_holidays import WINDOW_WEEKS, upcoming_holidays
from app.models.digital_twin import Airport, PassengerDemand, Route
from app.models.external import MarketRoute

# competition_level: LOW up to this many rival airlines, MODERATE up to the next, HIGH above it.
LOW_COMPETITION_MAX_RIVALS = 2
MODERATE_COMPETITION_MAX_RIVALS = 4
# demand_outlook thresholds.
STRONG_PASSENGER_GROWTH_PCT = 5.0
STRONG_HOLIDAYS = 2
STRONG_LOAD_FACTOR = 0.75
WEAK_LOAD_FACTOR = 0.6


def _today() -> date:
    return date.today()


def competition_level_for(rival_airlines: int) -> str:
    """LOW for 0-2 distinct rival airlines, MODERATE for 3-4, HIGH for 5 or more."""
    if rival_airlines <= LOW_COMPETITION_MAX_RIVALS:
        return "LOW"
    if rival_airlines <= MODERATE_COMPETITION_MAX_RIVALS:
        return "MODERATE"
    return "HIGH"


def demand_outlook_for(passenger_growth_pct: float | None, holidays: int, load_factor: float | None) -> str:
    """STRONG if (passenger growth >= 5% or holidays >= 2 in the next 8 weeks) and the route's historical load
    factor >= 0.75; otherwise WEAK if passenger growth < 0 or load factor < 0.6; otherwise STABLE.

    STRONG is tested first. A missing input never satisfies a condition (so it can only lead to STABLE).
    """
    growing = (passenger_growth_pct is not None and passenger_growth_pct >= STRONG_PASSENGER_GROWTH_PCT) or holidays >= STRONG_HOLIDAYS
    if growing and load_factor is not None and load_factor >= STRONG_LOAD_FACTOR:
        return "STRONG"
    if (passenger_growth_pct is not None and passenger_growth_pct < 0) or (
        load_factor is not None and load_factor < WEAK_LOAD_FACTOR
    ):
        return "WEAK"
    return "STABLE"


async def query_market_conditions(db: AsyncSession) -> dict:
    """Competition, national demand context and a precomputed demand outlook per twin route.

    Per route: `rival_airlines` is the number of distinct OpenFlights airlines flying it in either direction;
    `competition_level` is LOW (<= 2), MODERATE (3-4) or HIGH (>= 5). The national context holds the latest
    World Bank air-passenger growth (year over year, %), GDP growth (%) and the Indian public holidays in the
    next 8 weeks. `demand_outlook` is STRONG if (passenger growth >= 5% or >= 2 holidays) and the route's
    latest historical load factor >= 0.75; WEAK if passenger growth < 0 or load factor < 0.6; else STABLE.
    Missing data gives nulls (never invented values) and a note.
    """
    notes: list[str] = []
    latest = await world_bank.world_bank_latest(db)
    passengers, gdp = latest.get(world_bank.PASSENGERS), latest.get(world_bank.GDP_GROWTH)
    growth = passengers["yoy_pct"] if passengers else None
    if passengers is None:
        notes.append("No World Bank air passenger data: passenger growth is unknown.")
    elif growth is None:
        notes.append(f"World Bank air passengers for {passengers['year'] - 1} are missing: passenger growth is unknown.")
    if gdp is None:
        notes.append("No World Bank GDP growth data.")
    holiday_list = upcoming_holidays(_today())

    market_loaded = (await db.execute(select(func.count()).select_from(MarketRoute))).scalar_one() > 0
    if not market_loaded:
        notes.append("No OpenFlights market data: rival airlines and competition level are unknown.")

    origin, destination = Airport.__table__.alias("o"), Airport.__table__.alias("d")
    pairs = (
        await db.execute(
            select(Route.id, origin.c.code, destination.c.code)
            .select_from(
                Route.__table__.join(origin, Route.origin_id == origin.c.id).join(destination, Route.destination_id == destination.c.id)
            )
            .order_by(origin.c.code, destination.c.code)
        )
    ).all()

    routes = []
    for route_id, origin_code, destination_code in pairs:
        rivals = level = None
        if market_loaded:
            rivals = (
                await db.execute(
                    select(func.count(func.distinct(MarketRoute.airline_code))).where(
                        or_(
                            (MarketRoute.origin == origin_code) & (MarketRoute.destination == destination_code),
                            (MarketRoute.origin == destination_code) & (MarketRoute.destination == origin_code),
                        )
                    )
                )
            ).scalar_one()
            level = competition_level_for(rivals)
        load_factor = (
            await db.execute(
                select(PassengerDemand.historical_load_factor)
                .where(PassengerDemand.route_id == route_id)
                .order_by(PassengerDemand.period.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        routes.append(
            {
                "route": f"{origin_code}-{destination_code}",
                "rival_airlines": rivals,
                "competition_level": level,
                "historical_load_factor": load_factor,
                "demand_outlook": demand_outlook_for(growth, len(holiday_list), load_factor),
            }
        )
    return {
        "market": {
            "national": {
                "passenger_growth_pct": growth,
                "passenger_data_year": passengers["year"] if passengers else None,
                "gdp_growth_pct": gdp["value"] if gdp else None,
                "holidays_next_8_weeks": len(holiday_list),
                "holidays": holiday_list,
                "holiday_window_weeks": WINDOW_WEEKS,
            },
            "routes": routes,
            "notes": notes,
        }
    }

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digital_twin import Aircraft, Airport, PassengerDemand, Route
from app.seed.data import AIRCRAFT, AIRPORTS, DEMAND, ROUTES


async def run_seed(db: AsyncSession) -> None:
    """No-ops if any Airport row exists; otherwise inserts all seed data and commits it."""
    existing = (await db.execute(select(Airport))).scalars().first()
    if existing is not None:
        return  # already seeded

    airports_by_code: dict[str, Airport] = {}
    for row in AIRPORTS:
        airport = Airport(**row)
        db.add(airport)
        airports_by_code[row["code"]] = airport
    await db.flush()

    for row in AIRCRAFT:
        db.add(
            Aircraft(
                tail_number=row["tail_number"],
                aircraft_type=row["aircraft_type"],
                location_id=airports_by_code[row["location"]].id,
                status=row["status"],
                fuel_level_pct=row["fuel_level_pct"],
                flight_hours=row["flight_hours"],
                maintenance_status=row["maintenance_status"],
            )
        )

    routes_by_pair: dict[tuple[str, str], Route] = {}
    for row in ROUTES:
        route = Route(
            origin_id=airports_by_code[row["origin"]].id,
            destination_id=airports_by_code[row["destination"]].id,
            distance_km=row["distance_km"],
            current_frequency=row["current_frequency"],
            seats_per_flight=row["seats_per_flight"],
            average_fare_usd=row["average_fare_usd"],
            operating_cost_per_flight_usd=row["operating_cost_per_flight_usd"],
        )
        db.add(route)
        routes_by_pair[(row["origin"], row["destination"])] = route
    await db.flush()

    for row in DEMAND:
        db.add(
            PassengerDemand(
                route_id=routes_by_pair[row["route"]].id,
                period=row["period"],
                demand=row["demand"],
                historical_load_factor=row["historical_load_factor"],
            )
        )

    await db.commit()

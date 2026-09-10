from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digital_twin import Aircraft, Airport, PassengerDemand, Route


async def query_route_profitability(db: AsyncSession) -> dict:
    routes = (await db.execute(select(Route))).scalars().all()
    results = []
    for route in routes:
        demand_row = (
            await db.execute(select(PassengerDemand).where(PassengerDemand.route_id == route.id))
        ).scalars().first()
        origin = await db.get(Airport, route.origin_id)
        destination = await db.get(Airport, route.destination_id)
        results.append(
            {
                "route": f"{origin.code}-{destination.code}",
                "current_frequency": route.current_frequency,
                "distance_km": route.distance_km,
                "demand": demand_row.demand if demand_row else None,
                "historical_load_factor": demand_row.historical_load_factor if demand_row else None,
            }
        )
    return {"routes": results}


async def query_fleet_status(db: AsyncSession) -> dict:
    aircraft = (await db.execute(select(Aircraft))).scalars().all()
    results = []
    for unit in aircraft:
        location = await db.get(Airport, unit.location_id)
        results.append(
            {
                "tail_number": unit.tail_number,
                "aircraft_type": unit.aircraft_type,
                "location": location.code if location else None,
                "status": unit.status,
                "fuel_level_pct": unit.fuel_level_pct,
                "flight_hours": unit.flight_hours,
                "maintenance_status": unit.maintenance_status,
            }
        )
    return {"aircraft": results}

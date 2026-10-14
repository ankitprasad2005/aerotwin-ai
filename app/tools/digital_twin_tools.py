from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digital_twin import Aircraft, Airport, CrewMember, MaintenanceRecord, PassengerDemand, Route

# PassengerDemand.period is a quarter (e.g. "2026-Q3"); all economics here are weekly, matching
# Route.current_frequency (flights per week).
WEEKS_PER_QUARTER = 13
# Practical load-factor ceiling: some seats always go unsold, so added capacity is never assumed full.
MAX_LOAD_FACTOR = 0.9
# An open maintenance item due within this many flight hours makes an aircraft DUE_SOON.
DUE_SOON_HOURS = 100.0
# Remaining weekly duty hours below which a crew member is LIMITED: too few for a useful extra rotation.
MIN_USABLE_DUTY_HOURS = 10.0


def weekly_frequency_change_impact(
    *,
    current_frequency: int,
    seats_per_flight: int,
    historical_load_factor: float,
    quarterly_demand: int,
    average_fare_usd: float,
    operating_cost_per_flight_usd: float,
    change: int,
) -> dict | None:
    """Weekly revenue/cost/profit change (USD) and projected load factor if frequency changes by `change`.

    Today's weekly passengers are frequency x seats x historical load factor. Adding flights can
    capture unmet weekly demand, up to MAX_LOAD_FACTOR of the new capacity; removing flights can't
    add passengers and loses any that no longer fit. Returns None when the change would leave the
    route with no flights — that's cancelling the route, not a frequency change.
    """
    new_frequency = current_frequency + change
    if new_frequency <= 0:
        return None

    current_passengers = current_frequency * seats_per_flight * historical_load_factor
    new_passenger_ceiling = new_frequency * seats_per_flight * MAX_LOAD_FACTOR
    if change > 0:
        weekly_demand = quarterly_demand / WEEKS_PER_QUARTER
        new_passengers = max(current_passengers, min(weekly_demand, new_passenger_ceiling))
    else:
        new_passengers = min(current_passengers, new_passenger_ceiling)

    revenue = (new_passengers - current_passengers) * average_fare_usd
    cost = change * operating_cost_per_flight_usd
    return {
        "revenue_usd": round(revenue),
        "cost_usd": round(cost),
        "profit_usd": round(revenue - cost),
        "projected_load_factor": round(new_passengers / (new_frequency * seats_per_flight), 3),
    }


async def query_route_profitability(db: AsyncSession) -> dict:
    routes = (await db.execute(select(Route))).scalars().all()
    results = []
    for route in routes:
        demand_row = (
            await db.execute(
                select(PassengerDemand)
                .where(PassengerDemand.route_id == route.id)
                .order_by(PassengerDemand.period.desc())
            )
        ).scalars().first()
        origin = await db.get(Airport, route.origin_id)
        destination = await db.get(Airport, route.destination_id)
        entry = {
            "route": f"{origin.code}-{destination.code}",
            "current_frequency": route.current_frequency,
            "distance_km": route.distance_km,
            "demand": demand_row.demand if demand_row else None,
            "historical_load_factor": demand_row.historical_load_factor if demand_row else None,
            "seats_per_flight": route.seats_per_flight,
            "average_fare_usd": route.average_fare_usd,
            "operating_cost_per_flight_usd": route.operating_cost_per_flight_usd,
            "weekly_profit_usd": None,
            "impact_if_increase_by_one_weekly_flight": None,
            "impact_if_decrease_by_one_weekly_flight": None,
        }

        economics = (route.seats_per_flight, route.average_fare_usd, route.operating_cost_per_flight_usd)
        if demand_row is not None and None not in economics:
            # Computed here, not left to the LLM, so every agent works from the same grounded
            # numbers instead of inventing fares and costs.
            weekly_passengers = route.current_frequency * route.seats_per_flight * demand_row.historical_load_factor
            entry["weekly_profit_usd"] = round(
                weekly_passengers * route.average_fare_usd
                - route.current_frequency * route.operating_cost_per_flight_usd
            )
            impact_inputs = dict(
                current_frequency=route.current_frequency,
                seats_per_flight=route.seats_per_flight,
                historical_load_factor=demand_row.historical_load_factor,
                quarterly_demand=demand_row.demand,
                average_fare_usd=route.average_fare_usd,
                operating_cost_per_flight_usd=route.operating_cost_per_flight_usd,
            )
            entry["impact_if_increase_by_one_weekly_flight"] = weekly_frequency_change_impact(**impact_inputs, change=1)
            entry["impact_if_decrease_by_one_weekly_flight"] = weekly_frequency_change_impact(**impact_inputs, change=-1)

        results.append(entry)
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


def classify_airworthiness(aircraft_status: str, open_items: list[dict]) -> str:
    """GROUNDED, DUE_SOON or SERVICEABLE, from the aircraft's status and its open maintenance items.

    GROUNDED: the aircraft is in MAINTENANCE, or any open item is IN_PROGRESS or overdue.
    DUE_SOON: any open item is due within DUE_SOON_HOURS flight hours, or has open defects.
    """
    if aircraft_status == "MAINTENANCE" or any(
        item["status"] == "IN_PROGRESS" or item["overdue"] for item in open_items
    ):
        return "GROUNDED"
    if any(item["hours_until_due"] <= DUE_SOON_HOURS or item["open_defects"] > 0 for item in open_items):
        return "DUE_SOON"
    return "SERVICEABLE"


async def query_maintenance_status(db: AsyncSession) -> dict:
    """Each aircraft's open maintenance items and a deterministic airworthiness classification."""
    aircraft = (await db.execute(select(Aircraft).order_by(Aircraft.tail_number))).scalars().all()
    records = (
        await db.execute(select(MaintenanceRecord).order_by(MaintenanceRecord.due_at_flight_hours))
    ).scalars().all()
    records_by_aircraft = defaultdict(list)
    for record in records:
        records_by_aircraft[record.aircraft_id].append(record)

    results = []
    for unit in aircraft:
        open_items = []
        for record in records_by_aircraft[unit.id]:
            if record.status == "COMPLETED":
                continue
            hours_until_due = record.due_at_flight_hours - unit.flight_hours
            open_items.append(
                {
                    "check_type": record.check_type,
                    "status": record.status,
                    "due_at_flight_hours": record.due_at_flight_hours,
                    "hours_until_due": hours_until_due,
                    "overdue": hours_until_due < 0,
                    "open_defects": record.open_defects,
                    "notes": record.notes,
                }
            )
        results.append(
            {
                "tail_number": unit.tail_number,
                "aircraft_type": unit.aircraft_type,
                "flight_hours": unit.flight_hours,
                "aircraft_status": unit.status,
                "maintenance_status": unit.maintenance_status,
                "open_items": open_items,
                "total_open_defects": sum(item["open_defects"] for item in open_items),
                "next_due_in_hours": min((item["hours_until_due"] for item in open_items), default=None),
                "airworthiness": classify_airworthiness(unit.status, open_items),
            }
        )
    return {"maintenance": results}


def classify_crew_availability(status: str, remaining_duty_hours: float) -> str:
    """AVAILABLE, LIMITED or UNAVAILABLE for one crew member.

    UNAVAILABLE: not on AVAILABLE status, or no weekly duty hours left. LIMITED: fewer than
    MIN_USABLE_DUTY_HOURS left. Otherwise AVAILABLE.
    """
    if status != "AVAILABLE" or remaining_duty_hours <= 0:
        return "UNAVAILABLE"
    if remaining_duty_hours < MIN_USABLE_DUTY_HOURS:
        return "LIMITED"
    return "AVAILABLE"


async def query_crew_status(db: AsyncSession) -> dict:
    """Every crew member with base, qualification, duty hours and a deterministic availability."""
    rows = (
        await db.execute(
            select(CrewMember, Airport.code).join(Airport, Airport.id == CrewMember.base_id).order_by(CrewMember.employee_code)
        )
    ).all()
    results = []
    for member, base_code in rows:
        remaining = member.max_weekly_duty_hours - member.weekly_duty_hours
        results.append(
            {
                "employee_code": member.employee_code,
                "name": member.name,
                "role": member.role,
                "base": base_code,
                "qualified_aircraft_type": member.qualified_aircraft_type,
                "status": member.status,
                "weekly_duty_hours": member.weekly_duty_hours,
                "max_weekly_duty_hours": member.max_weekly_duty_hours,
                "remaining_duty_hours": remaining,
                "availability": classify_crew_availability(member.status, remaining),
            }
        )
    return {"crew": results}

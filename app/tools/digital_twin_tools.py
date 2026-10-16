from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digital_twin import Aircraft, Airport, CargoDemand, CrewMember, MaintenanceRecord, PassengerDemand, Route
from app.models.external import FuelPrice

# PassengerDemand.period is a quarter (e.g. "2026-Q3"); all economics here are weekly, matching
# Route.current_frequency (flights per week).
WEEKS_PER_QUARTER = 13
# Practical load-factor ceiling: some seats always go unsold, so added capacity is never assumed full.
MAX_LOAD_FACTOR = 0.9
# An open maintenance item due within this many flight hours makes an aircraft DUE_SOON.
DUE_SOON_HOURS = 100.0
# Remaining weekly duty hours below which a crew member is LIMITED: too few for a useful extra rotation.
MIN_USABLE_DUTY_HOURS = 10.0
# Practical cargo load ceiling: holds are never packed to 100% (weight, volume, shipment shapes).
MAX_CARGO_LOAD_FACTOR = 0.85
# Share of a flight's operating cost that is fuel, and the jet-fuel price (USD/gal) the seeded
# operating costs were written against (a documented seed-era assumption). A live price above or below
# the baseline scales the cost by FUEL_COST_SHARE of the relative change.
FUEL_COST_SHARE = 0.35
BASELINE_FUEL_USD_PER_GALLON = 2.20
# Weekly cost (USD) of moving ONE crew member to a route's origin: a one-way positioning seat plus
# a modest allowance. Charged per member who is not already based at the origin.
CREW_REPOSITIONING_COST_USD_PER_MEMBER = 300.0
# Weekly cost (USD) of ferrying ONE aircraft (empty one-way positioning flight) to a route's origin.
AIRCRAFT_REPOSITIONING_COST_USD = 4000.0
# Aircraft types a crew pair may be sought for when no flyable aircraft is at the route's origin.
A320_FAMILY = ("A320", "A321")


def fuel_cost_factor(latest_price_usd_per_gallon: float | None) -> float:
    """Multiplier for operating cost given the latest jet-fuel price; 1.0 when there is no price."""
    if latest_price_usd_per_gallon is None:
        return 1.0
    return 1 + FUEL_COST_SHARE * (latest_price_usd_per_gallon / BASELINE_FUEL_USD_PER_GALLON - 1)


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
    latest_fuel_price = (
        await db.execute(select(FuelPrice.usd_per_gallon).order_by(FuelPrice.price_date.desc()).limit(1))
    ).scalar_one_or_none()
    # Rounded so a 10% price move gives exactly 1.035 rather than 1.0349999...
    cost_factor = round(fuel_cost_factor(latest_fuel_price), 6)
    results = []
    for route in routes:
        operating_cost = (
            round(route.operating_cost_per_flight_usd * cost_factor, 2)
            if route.operating_cost_per_flight_usd is not None
            else None
        )
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
            "operating_cost_per_flight_usd": operating_cost,
            "fuel_price_usd_per_gallon": latest_fuel_price,
            "fuel_cost_factor": cost_factor,
            "weekly_profit_usd": None,
            "impact_if_increase_by_one_weekly_flight": None,
            "impact_if_decrease_by_one_weekly_flight": None,
        }

        economics = (route.seats_per_flight, route.average_fare_usd, operating_cost)
        if demand_row is not None and None not in economics:
            # Computed here, not left to the LLM, so every agent works from the same grounded
            # numbers instead of inventing fares and costs.
            weekly_passengers = route.current_frequency * route.seats_per_flight * demand_row.historical_load_factor
            entry["weekly_profit_usd"] = round(
                weekly_passengers * route.average_fare_usd
                - route.current_frequency * operating_cost
            )
            impact_inputs = dict(
                current_frequency=route.current_frequency,
                seats_per_flight=route.seats_per_flight,
                historical_load_factor=demand_row.historical_load_factor,
                quarterly_demand=demand_row.demand,
                average_fare_usd=route.average_fare_usd,
                operating_cost_per_flight_usd=operating_cost,
            )
            entry["impact_if_increase_by_one_weekly_flight"] = weekly_frequency_change_impact(**impact_inputs, change=1)
            entry["impact_if_decrease_by_one_weekly_flight"] = weekly_frequency_change_impact(**impact_inputs, change=-1)

        results.append(entry)
    return {"routes": results}


async def _route_origins(db: AsyncSession) -> list[tuple[str, str]]:
    """(route code, origin airport code) for every twin route, in the same order as the profitability tool."""
    routes = (await db.execute(select(Route))).scalars().all()
    results = []
    for route in routes:
        origin = await db.get(Airport, route.origin_id)
        destination = await db.get(Airport, route.destination_id)
        results.append((f"{origin.code}-{destination.code}", origin.code))
    return results


async def _flyable_aircraft(db: AsyncSession) -> list[dict]:
    """Aircraft that could fly an extra frequency: status AVAILABLE and not GROUNDED.

    Grounding comes from the same classify_airworthiness result the MAINTENANCE agent copies, so
    FLEET never assigns an aircraft MAINTENANCE reports as grounded. Each entry carries its
    airworthiness (SERVICEABLE or DUE_SOON) so callers can prefer SERVICEABLE.
    """
    maintenance = {m["tail_number"]: m["airworthiness"] for m in (await query_maintenance_status(db))["maintenance"]}
    aircraft = (await db.execute(select(Aircraft).order_by(Aircraft.tail_number))).scalars().all()
    flyable = []
    for unit in aircraft:
        airworthiness = maintenance[unit.tail_number]
        if unit.status != "AVAILABLE" or airworthiness == "GROUNDED":
            continue
        location = await db.get(Airport, unit.location_id)
        flyable.append(
            {
                "tail_number": unit.tail_number,
                "aircraft_type": unit.aircraft_type,
                "location": location.code if location else None,
                "airworthiness": airworthiness,
            }
        )
    return flyable


def assess_fleet_increase(origin: str, flyable: list[dict]) -> dict:
    """Aircraft to assign for one extra weekly flight from `origin`.

    Best candidate = already at the origin first, then SERVICEABLE before DUE_SOON, then tail number.
    An aircraft elsewhere costs AIRCRAFT_REPOSITIONING_COST_USD. No candidate: UNAVAILABLE.
    """
    if not flyable:
        return {
            "aircraft_tail_number": "NONE", "assignment_action": "NO_CHANGE",
            "aircraft_availability": "UNAVAILABLE", "expected_cost_impact": 0.0,
        }
    best = min(flyable, key=lambda a: (a["location"] != origin, a["airworthiness"] != "SERVICEABLE", a["tail_number"]))
    return {
        "aircraft_tail_number": best["tail_number"],
        "assignment_action": "ASSIGN_ADDITIONAL_AIRCRAFT",
        "aircraft_availability": "AVAILABLE",
        "expected_cost_impact": 0.0 if best["location"] == origin else AIRCRAFT_REPOSITIONING_COST_USD,
    }


async def query_fleet_status(db: AsyncSession) -> dict:
    """Every aircraft, plus a precomputed assignment per route for +1 and -1 weekly flight."""
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
    flyable = await _flyable_aircraft(db)
    no_change = {
        "aircraft_tail_number": "NONE", "assignment_action": "NO_CHANGE",
        "aircraft_availability": "AVAILABLE", "expected_cost_impact": 0.0,
    }
    assessments = [
        {
            "route": route,
            "if_increase_by_one_weekly_flight": assess_fleet_increase(origin, flyable),
            "if_decrease_by_one_weekly_flight": dict(no_change),
        }
        for route, origin in await _route_origins(db)
    ]
    return {"aircraft": results, "route_assessments": assessments}


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
    flyable = await _flyable_aircraft(db)
    no_change = {
        "crew_availability": "SUFFICIENT", "assignment_action": "NO_CHANGE",
        "assigned_crew": [], "expected_cost_impact": 0.0, "aircraft_type": None,
    }
    assessments = [
        {
            "route": route,
            "if_increase_by_one_weekly_flight": assess_crew_increase(origin, results, flyable),
            "if_decrease_by_one_weekly_flight": dict(no_change),
        }
        for route, origin in await _route_origins(db)
    ]
    return {"crew": results, "route_assessments": assessments}


def _candidate_aircraft_types(origin: str, flyable: list[dict]) -> list[str]:
    """Aircraft types an extra flight from `origin` could be flown with.

    The type of the best flyable (AVAILABLE, not grounded) aircraft at the origin, SERVICEABLE
    preferred; with none there, every A320-family type that has a flyable aircraft anywhere.
    """
    at_origin = sorted(
        (a for a in flyable if a["location"] == origin),
        key=lambda a: (a["airworthiness"] != "SERVICEABLE", a["tail_number"]),
    )
    if at_origin:
        return [at_origin[0]["aircraft_type"]]
    return [t for t in A320_FAMILY if any(a["aircraft_type"] == t for a in flyable)]


def assess_crew_increase(origin: str, crew: list[dict], flyable: list[dict]) -> dict:
    """Crew for one extra weekly flight from `origin`: one AVAILABLE captain and first officer of one type.

    Aircraft type: see _candidate_aircraft_types; the first type that can be crewed wins. Per role
    the pick is whoever has the most remaining duty hours, then the lowest employee code. In order:
    1. a pair both based at the origin: ASSIGN_ADDITIONAL_CREW, cost 0;
    2. a pair that shares another base (the pair moves together): REPOSITION_CREW, the base with the
       most combined remaining duty hours, then the lowest base code;
    3. otherwise a captain and first officer from different bases (any member already at the origin
       stays put): REPOSITION_CREW.
    Cost is CREW_REPOSITIONING_COST_USD_PER_MEMBER per member not based at the origin. No pair for
    any candidate type: INSUFFICIENT, NO_CHANGE, no crew, cost 0.
    """

    def pick(pool: list[dict]) -> dict | None:
        return min(pool, key=lambda m: (-m["remaining_duty_hours"], m["employee_code"]), default=None)

    def result(captain: dict, first_officer: dict, aircraft_type: str) -> dict:
        away = sum(1 for m in (captain, first_officer) if m["base"] != origin)
        return {
            "crew_availability": "SUFFICIENT",
            "assignment_action": "REPOSITION_CREW" if away else "ASSIGN_ADDITIONAL_CREW",
            "assigned_crew": [captain["employee_code"], first_officer["employee_code"]],
            "expected_cost_impact": away * CREW_REPOSITIONING_COST_USD_PER_MEMBER,
            "aircraft_type": aircraft_type,
        }

    candidate_types = _candidate_aircraft_types(origin, flyable)
    for aircraft_type in candidate_types:
        pools = {
            role: [
                m for m in crew
                if m["role"] == role and m["availability"] == "AVAILABLE" and m["qualified_aircraft_type"] == aircraft_type
            ]
            for role in ("CAPTAIN", "FIRST_OFFICER")
        }
        if not pools["CAPTAIN"] or not pools["FIRST_OFFICER"]:
            continue
        pairs = []  # (captain, first officer) per base where both roles are based
        for base in {m["base"] for m in pools["CAPTAIN"]} & {m["base"] for m in pools["FIRST_OFFICER"]}:
            pairs.append(
                (base, pick([m for m in pools["CAPTAIN"] if m["base"] == base]),
                 pick([m for m in pools["FIRST_OFFICER"] if m["base"] == base]))
            )
        at_origin = [p for p in pairs if p[0] == origin]
        if at_origin:
            return result(at_origin[0][1], at_origin[0][2], aircraft_type)
        if pairs:
            _, captain, first_officer = min(
                pairs, key=lambda p: (-(p[1]["remaining_duty_hours"] + p[2]["remaining_duty_hours"]), p[0])
            )
            return result(captain, first_officer, aircraft_type)
        by_origin_first = lambda m: (m["base"] != origin, -m["remaining_duty_hours"], m["employee_code"])  # noqa: E731
        return result(
            min(pools["CAPTAIN"], key=by_origin_first), min(pools["FIRST_OFFICER"], key=by_origin_first), aircraft_type
        )
    return {
        "crew_availability": "INSUFFICIENT", "assignment_action": "NO_CHANGE", "assigned_crew": [],
        "expected_cost_impact": 0.0, "aircraft_type": candidate_types[0] if len(candidate_types) == 1 else None,
    }


def weekly_cargo_change_impact(
    *,
    current_frequency: int,
    capacity_kg_per_flight: float,
    weekly_demand_kg: float,
    rate_usd_per_kg: float,
    handling_cost_usd_per_kg: float,
    change: int,
) -> dict | None:
    """Weekly cargo kg, revenue, handling cost and profit change (USD) if frequency changes by `change`.

    Cargo carried is weekly demand capped at MAX_CARGO_LOAD_FACTOR of capacity, so extra flights
    carry only demand that does not fit today, and fewer flights lose what no longer fits. Only
    handling cost is counted: flying the extra flight is the network agent's cost. Returns None
    when the change would leave the route with no flights.
    """
    new_frequency = current_frequency + change
    if new_frequency <= 0:
        return None

    def carried(frequency: int) -> float:
        return min(weekly_demand_kg, frequency * capacity_kg_per_flight * MAX_CARGO_LOAD_FACTOR)

    additional_kg = carried(new_frequency) - carried(current_frequency)
    revenue = additional_kg * rate_usd_per_kg
    cost = additional_kg * handling_cost_usd_per_kg
    return {
        "additional_kg": round(additional_kg),
        "revenue_usd": round(revenue),
        "cost_usd": round(cost),
        "profit_usd": round(revenue - cost),
    }


async def query_cargo_opportunities(db: AsyncSession) -> dict:
    """Cargo demand, load and precomputed one-flight impacts for every route that has cargo data."""
    routes = (await db.execute(select(Route))).scalars().all()
    results = []
    for route in routes:
        cargo = (
            await db.execute(
                select(CargoDemand).where(CargoDemand.route_id == route.id).order_by(CargoDemand.period.desc())
            )
        ).scalars().first()
        if cargo is None:
            continue
        origin = await db.get(Airport, route.origin_id)
        destination = await db.get(Airport, route.destination_id)
        weekly_capacity = route.current_frequency * cargo.capacity_kg_per_flight
        carried = min(cargo.weekly_demand_kg, weekly_capacity * MAX_CARGO_LOAD_FACTOR)
        impact_inputs = dict(
            current_frequency=route.current_frequency,
            capacity_kg_per_flight=cargo.capacity_kg_per_flight,
            weekly_demand_kg=cargo.weekly_demand_kg,
            rate_usd_per_kg=cargo.rate_usd_per_kg,
            handling_cost_usd_per_kg=cargo.handling_cost_usd_per_kg,
        )
        results.append(
            {
                "route": f"{origin.code}-{destination.code}",
                "current_frequency": route.current_frequency,
                "period": cargo.period,
                "weekly_demand_kg": cargo.weekly_demand_kg,
                "capacity_kg_per_flight": cargo.capacity_kg_per_flight,
                "rate_usd_per_kg": cargo.rate_usd_per_kg,
                "handling_cost_usd_per_kg": cargo.handling_cost_usd_per_kg,
                "weekly_capacity_kg": weekly_capacity,
                "weekly_carried_kg": carried,
                "cargo_load_factor": round(carried / weekly_capacity, 3) if weekly_capacity else 0.0,
                "impact_if_increase_by_one_weekly_flight": weekly_cargo_change_impact(**impact_inputs, change=1),
                "impact_if_decrease_by_one_weekly_flight": weekly_cargo_change_impact(**impact_inputs, change=-1),
            }
        )
    return {"cargo": results}

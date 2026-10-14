import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class Airport(TimestampedBase):
    __tablename__ = "airports"

    code: Mapped[str] = mapped_column(String(4), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)


class Aircraft(TimestampedBase):
    __tablename__ = "aircraft"

    tail_number: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    aircraft_type: Mapped[str] = mapped_column(String, nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("airports.id"), nullable=False, index=True
    )
    # plain string for Phase 1; formalize as an Enum type if validation needs grow
    status: Mapped[str] = mapped_column(String, nullable=False, default="AVAILABLE")
    fuel_level_pct: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    flight_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    maintenance_status: Mapped[str] = mapped_column(String, nullable=False, default="NORMAL")


class MaintenanceRecord(TimestampedBase):
    """One maintenance item (check or defect repair) for an aircraft."""

    __tablename__ = "maintenance_records"

    aircraft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("aircraft.id"), nullable=False, index=True
    )
    # A_CHECK / C_CHECK / ENGINE_INSPECTION / DEFECT_REPAIR; SCHEDULED / IN_PROGRESS / COMPLETED
    # (plain strings, like Aircraft.status)
    check_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    # Aircraft.flight_hours value at which the item falls due.
    due_at_flight_hours: Mapped[float] = mapped_column(Float, nullable=False)
    open_defects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str] = mapped_column(String, nullable=False, default="")


class CrewMember(TimestampedBase):
    __tablename__ = "crew_members"

    employee_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # CAPTAIN / FIRST_OFFICER / CABIN_CREW (plain strings, like Aircraft.status)
    role: Mapped[str] = mapped_column(String, nullable=False)
    base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("airports.id"), nullable=False, index=True)
    # Aircraft type the member is rated for; ANY for cabin crew.
    qualified_aircraft_type: Mapped[str] = mapped_column(String, nullable=False)
    # AVAILABLE / ON_LEAVE / SICK
    status: Mapped[str] = mapped_column(String, nullable=False, default="AVAILABLE")
    weekly_duty_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_weekly_duty_hours: Mapped[float] = mapped_column(Float, nullable=False, default=40.0)


class Route(TimestampedBase):
    __tablename__ = "routes"

    origin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("airports.id"), nullable=False, index=True
    )
    destination_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("airports.id"), nullable=False, index=True
    )
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    current_frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Route economics (USD). Nullable: a route without them still appears in the network data,
    # just without computed profit impacts.
    seats_per_flight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    average_fare_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_cost_per_flight_usd: Mapped[float | None] = mapped_column(Float, nullable=True)


# aircraft/route are always assigned at creation in Phase 1 scope
class Flight(TimestampedBase):
    __tablename__ = "flights"

    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("routes.id"), nullable=False, index=True
    )
    aircraft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("aircraft.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="SCHEDULED")


class PassengerDemand(TimestampedBase):
    __tablename__ = "passenger_demand"
    __table_args__ = (
        UniqueConstraint("route_id", "period", name="uq_passenger_demand_route_period"),
    )

    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("routes.id"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String, nullable=False)
    demand: Mapped[int] = mapped_column(Integer, nullable=False)
    historical_load_factor: Mapped[float] = mapped_column(Float, nullable=False)


class CargoDemand(TimestampedBase):
    """Belly-cargo demand and economics for a route in one period (weekly figures, USD)."""

    __tablename__ = "cargo_demand"
    __table_args__ = (
        UniqueConstraint("route_id", "period", name="uq_cargo_demand_route_period"),
    )

    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("routes.id"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String, nullable=False)
    weekly_demand_kg: Mapped[float] = mapped_column(Float, nullable=False)
    capacity_kg_per_flight: Mapped[float] = mapped_column(Float, nullable=False)
    rate_usd_per_kg: Mapped[float] = mapped_column(Float, nullable=False)
    handling_cost_usd_per_kg: Mapped[float] = mapped_column(Float, nullable=False)

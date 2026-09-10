import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
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
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("airports.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="AVAILABLE")
    fuel_level_pct: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    flight_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    maintenance_status: Mapped[str] = mapped_column(String, nullable=False, default="NORMAL")


class Route(TimestampedBase):
    __tablename__ = "routes"

    origin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("airports.id"), nullable=False)
    destination_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("airports.id"), nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    current_frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Flight(TimestampedBase):
    __tablename__ = "flights"

    route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("routes.id"), nullable=False)
    aircraft_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("aircraft.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="SCHEDULED")


class PassengerDemand(TimestampedBase):
    __tablename__ = "passenger_demand"

    route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("routes.id"), nullable=False)
    period: Mapped[str] = mapped_column(String, nullable=False)
    demand: Mapped[int] = mapped_column(Integer, nullable=False)
    historical_load_factor: Mapped[float] = mapped_column(Float, nullable=False)

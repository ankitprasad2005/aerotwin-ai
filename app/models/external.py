import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase

# Status values of DatasetSnapshot.status.
SNAPSHOT_SUCCESS = "SUCCESS"
SNAPSHOT_FAILED = "FAILED"
SNAPSHOT_FALLBACK = "FALLBACK"


class DatasetSnapshot(TimestampedBase):
    """One attempt to download and normalise an external dataset."""

    __tablename__ = "dataset_snapshots"

    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # SUCCESS / FAILED / FALLBACK
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    local_path: Mapped[str | None] = mapped_column(String, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class MarketRoute(TimestampedBase):
    """An airline operating a route (OpenFlights)."""

    __tablename__ = "market_routes"
    __table_args__ = (Index("ix_market_routes_origin_destination", "origin", "destination"),)

    airline_code: Mapped[str] = mapped_column(String, nullable=False)
    airline_name: Mapped[str | None] = mapped_column(String, nullable=True)
    origin: Mapped[str] = mapped_column(String(4), nullable=False)
    destination: Mapped[str] = mapped_column(String(4), nullable=False)
    stops: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    equipment: Mapped[str] = mapped_column(String, nullable=False, default="")
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dataset_snapshots.id"), nullable=True)


class FuelPrice(TimestampedBase):
    __tablename__ = "fuel_prices"
    __table_args__ = (UniqueConstraint("series", "price_date", name="uq_fuel_prices_series_price_date"),)

    series: Mapped[str] = mapped_column(String, nullable=False)
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    usd_per_gallon: Mapped[float] = mapped_column(Float, nullable=False)


class FxRate(TimestampedBase):
    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("base", "quote", "rate_date", name="uq_fx_rates_base_quote_rate_date"),)

    base: Mapped[str] = mapped_column(String, nullable=False)
    quote: Mapped[str] = mapped_column(String, nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)


class DgcaTraffic(TimestampedBase):
    """Indian domestic traffic for one airline in one month (DGCA)."""

    __tablename__ = "dgca_traffic"
    __table_args__ = (UniqueConstraint("period", "airline", name="uq_dgca_traffic_period_airline"),)

    period: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "2026-04"
    airline: Mapped[str] = mapped_column(String, nullable=False)
    passengers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    market_share_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_factor_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class WebSearchCache(TimestampedBase):
    __tablename__ = "web_search_cache"

    query: Mapped[str] = mapped_column(String, nullable=False, unique=True)  # normalised: lower-case, collapsed spaces
    results: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DecisionWeightProfile(TimestampedBase):
    __tablename__ = "decision_weight_profiles"

    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    weights: Mapped[dict] = mapped_column(JSONB, nullable=False)

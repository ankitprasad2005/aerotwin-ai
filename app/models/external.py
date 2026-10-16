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


class OilPrice(TimestampedBase):
    """One daily Brent crude spot price (EIA RBRTE), USD per barrel."""

    __tablename__ = "oil_prices"
    __table_args__ = (UniqueConstraint("series", "price_date", name="uq_oil_prices_series_price_date"),)

    series: Mapped[str] = mapped_column(String, nullable=False)
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    usd_per_barrel: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dataset_snapshots.id"), nullable=True)


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


class WeatherObservation(TimestampedBase):
    """The latest METAR of one twin airport (aviationweather.gov)."""

    __tablename__ = "weather_observations"
    __table_args__ = (UniqueConstraint("airport", "observed_at", name="uq_weather_observations_airport_observed_at"),)

    airport: Mapped[str] = mapped_column(String(4), nullable=False)  # IATA, e.g. "BOM"
    icao: Mapped[str] = mapped_column(String(4), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    flight_category: Mapped[str] = mapped_column(String, nullable=False)  # VFR / MVFR / IFR / LIFR
    wind_kt: Mapped[float] = mapped_column(Float, nullable=False)
    gust_kt: Mapped[float | None] = mapped_column(Float, nullable=True)
    visibility_sm: Mapped[float | None] = mapped_column(Float, nullable=True)
    ceiling_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dataset_snapshots.id"), nullable=True)


class WeatherForecast(TimestampedBase):
    """One day of the 7-day forecast for a twin airport (Open-Meteo)."""

    __tablename__ = "weather_forecasts"
    __table_args__ = (UniqueConstraint("airport", "forecast_date", name="uq_weather_forecasts_airport_forecast_date"),)

    airport: Mapped[str] = mapped_column(String(4), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    precipitation_mm: Mapped[float] = mapped_column(Float, nullable=False)
    max_gust_kmh: Mapped[float] = mapped_column(Float, nullable=False)
    weather_code: Mapped[int] = mapped_column(Integer, nullable=False)
    thunderstorm: Mapped[bool] = mapped_column(Boolean, nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dataset_snapshots.id"), nullable=True)


class AirworthinessDirective(TimestampedBase):
    """An FAA airworthiness directive (Federal Register final rule) that concerns one or more twin aircraft types."""

    __tablename__ = "airworthiness_directives"

    document_number: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    publication_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    html_url: Mapped[str] = mapped_column(String, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    aircraft_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # twin types, e.g. ["A320", "A321"]
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dataset_snapshots.id"), nullable=True)


class WeatherTaf(TimestampedBase):
    """The latest terminal forecast (TAF) of one twin airport, with its next-24-hour summary (aviationweather.gov)."""

    __tablename__ = "weather_tafs"
    __table_args__ = (UniqueConstraint("airport", "issued_at", name="uq_weather_tafs_airport_issued_at"),)

    airport: Mapped[str] = mapped_column(String(4), nullable=False)  # IATA, e.g. "BOM"
    icao: Mapped[str] = mapped_column(String(4), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    worst_flight_category_24h: Mapped[str] = mapped_column(String, nullable=False)  # VFR / MVFR / IFR / LIFR
    thunderstorm_24h: Mapped[bool] = mapped_column(Boolean, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dataset_snapshots.id"), nullable=True)

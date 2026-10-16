"""The generic data explorer: a registry of browsable tables plus the query helpers behind /api/data.

ADDING A DATASET = ONE ENTRY in EXPLORER_TABLES below, e.g.

    "aai_traffic": ExplorerTable(
        title="AAI monthly airport traffic",
        category="Air traffic",                       # one of CATEGORIES
        description="Passengers and movements per airport per month.",
        model=AaiTraffic,                             # SQLAlchemy model
        columns=(
            C("period", "Period", "text"),
            C("passengers", "Passengers", "integer", "pax"),
        ),                                            # type: text|integer|number|boolean|date|datetime|json|id
        searchable=("airport", "period"),             # columns matched by the free-text search
        default_sort=("period", "desc"),
        source="aai_traffic",                         # optional dataset source key (snapshot / refresh status)
    ),

Every SQLAlchemy model must be registered or listed in EXCLUDED_TABLES with a reason (a test enforces this).
"""
import csv
import io
import json
import math
import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Base
from app.models.digital_twin import (
    Aircraft, Airport, CargoDemand, CrewMember, Flight, MaintenanceRecord, PassengerDemand, Route,
)
from app.models.external import (
    SNAPSHOT_FAILED, AirportTrafficLive, AirportTrafficMonthly, AirTrafficSnapshot, AirworthinessDirective, DatasetSnapshot,
    DecisionWeightProfile, DgcaTraffic, FuelPrice, FxRate, IndiaAirport, IndiaRunway, MarketRoute, OilPrice, WebSearchCache,
    WeatherForecast, WeatherObservation, WeatherTaf, WorldBankIndicator,
)

CATEGORIES = (
    "Airports", "Air traffic", "Weather", "Fuel & prices", "Market & economy", "Safety", "Web", "Digital twin", "System",
)
COLUMN_TYPES = ("text", "integer", "number", "boolean", "date", "datetime", "json", "id")
MAX_LIMIT = 500
CSV_BATCH = 1000
MAX_CSV_ROWS = 200_000


@dataclass(frozen=True)
class Column:
    name: str
    label: str
    type: str = "text"
    unit: str | None = None


def C(name: str, label: str, type: str = "text", unit: str | None = None) -> Column:  # noqa: N802 (terse registry helper)
    return Column(name, label, type, unit)


@dataclass(frozen=True)
class ExplorerTable:
    title: str
    category: str
    description: str
    model: type[Base]
    columns: tuple[Column, ...]
    searchable: tuple[str, ...]
    default_sort: tuple[str, str]
    source: str | None = None  # dataset source key whose latest snapshot gives "last refreshed"


_ID = C("id", "ID", "id")

EXPLORER_TABLES: dict[str, ExplorerTable] = {
    "market_routes": ExplorerTable(
        "OpenFlights routes", "Market & economy", "Airlines operating each route between the twin's airports.",
        MarketRoute,
        (C("airline_code", "Airline code"), C("airline_name", "Airline"), C("origin", "Origin"),
         C("destination", "Destination"), C("stops", "Stops", "integer"), C("equipment", "Equipment")),
        ("airline_code", "airline_name", "origin", "destination", "equipment"), ("origin", "asc"), "openflights",
    ),
    "fuel_prices": ExplorerTable(
        "EIA jet fuel price", "Fuel & prices", "Daily U.S. Gulf Coast kerosene-type jet fuel spot price.", FuelPrice,
        (C("series", "Series"), C("price_date", "Date", "date"), C("usd_per_gallon", "USD per gallon", "number", "USD/gal")),
        ("series",), ("price_date", "desc"), "eia_jet_fuel",
    ),
    "oil_prices": ExplorerTable(
        "EIA Brent crude price", "Fuel & prices", "Daily Europe Brent crude spot price FOB.", OilPrice,
        (C("series", "Series"), C("price_date", "Date", "date"), C("usd_per_barrel", "USD per barrel", "number", "USD/bbl")),
        ("series",), ("price_date", "desc"), "eia_brent",
    ),
    "fx_rates": ExplorerTable(
        "Exchange rates", "Market & economy", "Daily reference exchange rates (ECB via Frankfurter).", FxRate,
        (C("base", "Base"), C("quote", "Quote"), C("rate_date", "Date", "date"), C("rate", "Rate", "number")),
        ("base", "quote"), ("rate_date", "desc"), "fx",
    ),
    "dgca_traffic": ExplorerTable(
        "DGCA domestic traffic", "Air traffic", "Indian domestic passenger traffic by airline and month.", DgcaTraffic,
        (C("period", "Period"), C("airline", "Airline"), C("passengers", "Passengers", "integer", "pax"),
         C("market_share_pct", "Market share", "number", "%"), C("load_factor_pct", "Load factor", "number", "%"),
         C("source_url", "Source URL"), C("is_fallback", "Bundled fallback", "boolean")),
        ("period", "airline"), ("period", "desc"), "dgca",
    ),
    "weather_observations": ExplorerTable(
        "Weather observations (METAR)", "Weather", "Latest METAR of each twin airport (aviationweather.gov).",
        WeatherObservation,
        (C("airport", "Airport"), C("icao", "ICAO"), C("observed_at", "Observed at", "datetime"),
         C("flight_category", "Flight category"), C("wind_kt", "Wind", "number", "kt"), C("gust_kt", "Gust", "number", "kt"),
         C("visibility_sm", "Visibility", "number", "SM"), C("ceiling_ft", "Ceiling", "number", "ft"),
         C("raw_text", "Raw METAR")),
        ("airport", "icao", "flight_category", "raw_text"), ("observed_at", "desc"), "aviation_weather",
    ),
    "weather_forecasts": ExplorerTable(
        "Weather forecasts", "Weather", "7-day daily forecast for each twin airport (Open-Meteo).", WeatherForecast,
        (C("airport", "Airport"), C("forecast_date", "Date", "date"),
         C("precipitation_mm", "Precipitation", "number", "mm"), C("max_gust_kmh", "Max gust", "number", "km/h"),
         C("weather_code", "Weather code", "integer"), C("thunderstorm", "Thunderstorm", "boolean")),
        ("airport",), ("forecast_date", "desc"), "open_meteo",
    ),
    "weather_tafs": ExplorerTable(
        "Terminal forecasts (TAF)", "Weather", "Latest TAF of each twin airport with a 24-hour summary.", WeatherTaf,
        (C("airport", "Airport"), C("icao", "ICAO"), C("issued_at", "Issued at", "datetime"),
         C("valid_from", "Valid from", "datetime"), C("valid_to", "Valid to", "datetime"),
         C("worst_flight_category_24h", "Worst category 24h"), C("thunderstorm_24h", "Thunderstorm 24h", "boolean"),
         C("raw_text", "Raw TAF")),
        ("airport", "icao", "worst_flight_category_24h", "raw_text"), ("issued_at", "desc"), "aviation_weather_taf",
    ),
    "airworthiness_directives": ExplorerTable(
        "Airworthiness directives", "Safety", "FAA airworthiness directives concerning the twin's aircraft types.",
        AirworthinessDirective,
        (C("document_number", "Document"), C("title", "Title"), C("publication_date", "Published", "date"),
         C("aircraft_types", "Aircraft types", "json"), C("abstract", "Abstract"), C("html_url", "URL")),
        ("document_number", "title", "abstract", "aircraft_types"), ("publication_date", "desc"),
        "faa_airworthiness_directives",
    ),
    "world_bank_indicators": ExplorerTable(
        "World Bank indicators", "Market & economy", "Macro-economic indicators for India by year.", WorldBankIndicator,
        (C("indicator", "Indicator"), C("year", "Year", "integer"), C("value", "Value", "number")),
        ("indicator",), ("year", "desc"), "world_bank",
    ),
    "web_search_cache": ExplorerTable(
        "Web search cache", "Web", "Cached web search queries and their results.", WebSearchCache,
        (C("query", "Query"), C("result_count", "Results", "integer"), C("fetched_at", "Fetched at", "datetime"),
         C("results", "Results (JSON)", "json")),
        ("query",), ("fetched_at", "desc"),
    ),
    "dataset_snapshots": ExplorerTable(
        "Dataset snapshots", "System", "Every attempt to download and normalise an external dataset.", DatasetSnapshot,
        (_ID, C("source", "Source"), C("fetched_at", "Fetched at", "datetime"), C("status", "Status"),
         C("row_count", "Rows", "integer"), C("source_url", "Source URL"), C("checksum", "Checksum"),
         C("error", "Error"), C("details", "Details", "json")),
        ("source", "status", "error"), ("fetched_at", "desc"),
    ),
    "decision_weight_profiles": ExplorerTable(
        "Decision weight profiles", "System", "Saved weightings of the decision criteria.", DecisionWeightProfile,
        (C("name", "Name"), C("weights", "Weights", "json"), C("updated_at", "Updated at", "datetime")),
        ("name",), ("name", "asc"),
    ),
    "airports": ExplorerTable(
        "Airports", "Digital twin", "The airports of the digital twin.", Airport,
        (C("code", "Code"), C("name", "Name"), C("city", "City"), C("country", "Country")),
        ("code", "name", "city", "country"), ("code", "asc"),
    ),
    "aircraft": ExplorerTable(
        "Aircraft", "Digital twin", "The twin's fleet.", Aircraft,
        (C("tail_number", "Tail"), C("aircraft_type", "Type"), C("status", "Status"),
         C("fuel_level_pct", "Fuel level", "number", "%"), C("flight_hours", "Flight hours", "number", "h"),
         C("maintenance_status", "Maintenance"), C("location_id", "Location ID", "id")),
        ("tail_number", "aircraft_type", "status", "maintenance_status"), ("tail_number", "asc"),
    ),
    "routes": ExplorerTable(
        "Routes", "Digital twin", "The twin's route network and its economics.", Route,
        (C("origin_id", "Origin ID", "id"), C("destination_id", "Destination ID", "id"),
         C("distance_km", "Distance", "number", "km"), C("current_frequency", "Frequency", "integer", "per week"),
         C("seats_per_flight", "Seats per flight", "integer"), C("average_fare_usd", "Average fare", "number", "USD"),
         C("operating_cost_per_flight_usd", "Cost per flight", "number", "USD")),
        ("origin_id", "destination_id"), ("distance_km", "desc"),
    ),
    "flights": ExplorerTable(
        "Flights", "Digital twin", "Flights assigned to a route and an aircraft.", Flight,
        (_ID, C("route_id", "Route ID", "id"), C("aircraft_id", "Aircraft ID", "id"), C("status", "Status")),
        ("status",), ("status", "asc"),
    ),
    "crew_members": ExplorerTable(
        "Crew members", "Digital twin", "Pilots and cabin crew.", CrewMember,
        (C("employee_code", "Code"), C("name", "Name"), C("role", "Role"),
         C("qualified_aircraft_type", "Qualified type"), C("status", "Status"),
         C("weekly_duty_hours", "Weekly duty", "number", "h"), C("max_weekly_duty_hours", "Max weekly duty", "number", "h")),
        ("employee_code", "name", "role", "qualified_aircraft_type", "status"), ("employee_code", "asc"),
    ),
    "maintenance_records": ExplorerTable(
        "Maintenance records", "Digital twin", "Checks and defect repairs per aircraft.", MaintenanceRecord,
        (C("aircraft_id", "Aircraft ID", "id"), C("check_type", "Check"), C("status", "Status"),
         C("due_at_flight_hours", "Due at", "number", "h"), C("open_defects", "Open defects", "integer"),
         C("notes", "Notes")),
        ("check_type", "status", "notes"), ("due_at_flight_hours", "asc"),
    ),
    "passenger_demand": ExplorerTable(
        "Passenger demand", "Digital twin", "Passenger demand and historical load factor per route and period.",
        PassengerDemand,
        (C("route_id", "Route ID", "id"), C("period", "Period"), C("demand", "Demand", "integer", "pax"),
         C("historical_load_factor", "Historical load factor", "number")),
        ("period",), ("period", "desc"),
    ),
    "cargo_demand": ExplorerTable(
        "Cargo demand", "Digital twin", "Weekly belly-cargo demand per route and period.", CargoDemand,
        (C("route_id", "Route ID", "id"), C("period", "Period"), C("weekly_demand_kg", "Weekly demand", "number", "kg"),
         C("capacity_kg_per_flight", "Capacity per flight", "number", "kg")),
        ("period",), ("period", "desc"),
    ),
    "india_airports": ExplorerTable(
        "Indian airports (OurAirports)", "Airports", "Every Indian aerodrome with codes, location, elevation and frequencies.",
        IndiaAirport,
        (C("ident", "Ident"), C("icao_code", "ICAO"), C("iata_code", "IATA"), C("name", "Name"), C("airport_type", "Type"),
         C("municipality", "City"), C("latitude_deg", "Latitude", "number", "deg"), C("longitude_deg", "Longitude", "number", "deg"),
         C("elevation_ft", "Elevation", "number", "ft"), C("scheduled_service", "Scheduled service", "boolean"),
         C("frequency_count", "Frequencies", "integer")),
        ("ident", "icao_code", "iata_code", "name", "municipality", "airport_type"), ("name", "asc"), "ourairports_india",
    ),
    "india_runways": ExplorerTable(
        "Indian runways (OurAirports)", "Airports", "Runways of Indian aerodromes: length, width, surface and lighting.",
        IndiaRunway,
        (C("airport_ident", "Airport"), C("le_ident", "Runway end"), C("he_ident", "Opposite end"),
         C("length_ft", "Length", "number", "ft"), C("width_ft", "Width", "number", "ft"), C("surface", "Surface"),
         C("lighted", "Lighted", "boolean"), C("closed", "Closed", "boolean")),
        ("airport_ident", "surface"), ("length_ft", "desc"), "ourairports_india",
    ),
    "airport_traffic_monthly": ExplorerTable(
        "AAI monthly airport traffic", "Airports", "Monthly aircraft movements, passengers and freight per Indian airport (AAI).",
        AirportTrafficMonthly,
        (C("airport_name", "Airport"), C("iata_code", "IATA"), C("icao_code", "ICAO"), C("period", "Month"),
         C("aircraft_movements", "Movements", "integer"), C("passengers", "Passengers", "integer", "pax"),
         C("freight_tonnes", "Freight", "number", "t"), C("movements_domestic", "Domestic movements", "integer"),
         C("movements_international", "International movements", "integer"),
         C("passengers_domestic", "Domestic passengers", "integer", "pax"),
         C("passengers_international", "International passengers", "integer", "pax"),
         C("movements_yoy_pct", "Movements YoY", "number", "%"), C("passengers_yoy_pct", "Passengers YoY", "number", "%"),
         C("freight_yoy_pct", "Freight YoY", "number", "%")),
        ("airport_name", "iata_code", "icao_code", "period"), ("period", "desc"), "aai_traffic",
    ),
    "air_traffic_snapshots": ExplorerTable(
        "Live air traffic over India", "Air traffic", "Aircraft over India at each OpenSky snapshot (airborne and on ground).",
        AirTrafficSnapshot,
        (C("taken_at", "Taken at", "datetime"), C("aircraft_over_india", "Aircraft over India", "integer"),
         C("airborne", "Airborne", "integer"), C("on_ground", "On ground", "integer")),
        ("taken_at",), ("taken_at", "desc"), "opensky_live",
    ),
    "airport_traffic_live": ExplorerTable(
        "Live traffic near airports", "Air traffic", "Aircraft near each major Indian airport at each OpenSky snapshot.",
        AirportTrafficLive,
        (C("taken_at", "Taken at", "datetime"), C("airport", "Airport"), C("icao", "ICAO"),
         C("aircraft_within_radius", "Aircraft nearby", "integer"), C("on_ground_nearby", "On ground", "integer"),
         C("airborne_nearby", "Airborne", "integer"), C("arrivals_last_24h", "Arrivals (prev. day)", "integer"),
         C("departures_last_24h", "Departures (prev. day)", "integer")),
        ("airport", "icao"), ("taken_at", "desc"), "opensky_live",
    ),
}

_RUN_HISTORY = "Orchestration run history: prompts and traces are shown on the Runs and Events pages, not as raw tables."
EXCLUDED_TABLES: dict[str, str] = {
    name: _RUN_HISTORY
    for name in (
        "orchestration_runs", "run_iterations", "agent_executions", "context_snapshots", "llm_executions",
        "tool_executions", "agent_messages", "decisions", "events",
    )
}


class ExplorerError(ValueError):
    """An invalid sort, filter or filter value (surfaced as HTTP 422)."""


def _column(table: ExplorerTable, name: str) -> Column:
    for column in table.columns:
        if column.name == name:
            return column
    raise ExplorerError(f"Unknown column: {name}")


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _contains(attr: Any, text: str):
    return cast(attr, String).ilike(f"%{_escape_like(text)}%", escape="\\")


def _filter_clause(table: ExplorerTable, name: str, raw: str):
    column = _column(table, name)
    attr = getattr(table.model, name)
    try:
        if column.type == "integer":
            return attr == int(raw)
        if column.type == "number":
            return attr == float(raw)
        if column.type == "boolean":
            lowered = raw.strip().lower()
            if lowered in ("true", "1", "yes"):
                return attr.is_(True)
            if lowered in ("false", "0", "no"):
                return attr.is_(False)
            raise ValueError(raw)
        if column.type == "date":
            return attr == date.fromisoformat(raw)
    except ValueError:
        raise ExplorerError(f"Invalid value for {name}: {raw!r}") from None
    return _contains(attr, raw)  # text, datetime, json, id: case-insensitive "contains"


def build_query(
    table: ExplorerTable, *, q: str = "", sort: str | None = None, order: str | None = None,
    filters: Mapping[str, str] | None = None,
) -> tuple[Select, Select]:
    """(rows statement, count statement) for the filtered, sorted table. Raises ExplorerError on bad input."""
    model = table.model
    clauses = []
    if q.strip():
        clauses.append(or_(*[_contains(getattr(model, n), q.strip()) for n in table.searchable]))
    for name, raw in (filters or {}).items():
        if raw != "":
            clauses.append(_filter_clause(table, name, raw))
    sort_name, sort_order = table.default_sort
    if sort:
        _column(table, sort)
        sort_name, sort_order = sort, order or "asc"
    elif order:
        sort_order = order
    sort_attr = getattr(model, sort_name)
    ordering = [sort_attr.desc() if sort_order == "desc" else sort_attr.asc()]
    if hasattr(model, "id"):
        ordering.append(model.id.asc())
    rows = select(*[getattr(model, c.name) for c in table.columns]).where(*clauses).order_by(*ordering)
    count = select(func.count()).select_from(model).where(*clauses)
    return rows, count


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def row_dict(table: ExplorerTable, row: Any) -> dict[str, Any]:
    return {c.name: json_safe(v) for c, v in zip(table.columns, row, strict=True)}


async def fetch_rows(
    db: AsyncSession, table: ExplorerTable, rows_stmt: Select, count_stmt: Select, limit: int, offset: int
) -> dict[str, Any]:
    total = (await db.execute(count_stmt)).scalar_one()
    result = await db.execute(rows_stmt.limit(limit).offset(offset))
    return {"total": total, "rows": [row_dict(table, r) for r in result.all()]}


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


async def stream_csv(db: AsyncSession, table: ExplorerTable, rows_stmt: Select) -> AsyncIterator[str]:
    def render(records: list[list[str]]) -> str:
        buffer = io.StringIO()
        csv.writer(buffer).writerows(records)
        return buffer.getvalue()

    yield render([[c.name for c in table.columns]])
    offset = 0
    while offset < MAX_CSV_ROWS:
        batch = (await db.execute(rows_stmt.limit(CSV_BATCH).offset(offset))).all()
        if not batch:
            return
        yield render([[_csv_cell(json_safe(v)) for v in row] for row in batch])
        if len(batch) < CSV_BATCH:
            return
        offset += CSV_BATCH


async def last_refreshed(db: AsyncSession) -> dict[str, datetime]:
    """Latest non-failed snapshot time per dataset source."""
    stmt = (
        select(DatasetSnapshot.source, func.max(DatasetSnapshot.fetched_at))
        .where(DatasetSnapshot.status != SNAPSHOT_FAILED)
        .group_by(DatasetSnapshot.source)
    )
    return {source: at for source, at in (await db.execute(stmt)).all()}

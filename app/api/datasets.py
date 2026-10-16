from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.datasets import queries
from app.datasets.air_traffic import AIRPORTS_BY_IATA, air_traffic_history, latest_air_traffic
from app.datasets.weather import AIRPORT_STATIONS
from app.datasets.refresh import SOURCE_INFO, refresh_all, validate_sources
from app.datasets.world_bank import INDICATORS, world_bank_latest
from app.models.external import DatasetSnapshot

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

MAX_DAYS = 3650


class RefreshRequest(BaseModel):
    sources: list[str] | None = None

    @field_validator("sources")
    @classmethod
    def _known_sources(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            validate_sources(value)  # ValueError -> 422
        return value


def snapshot_summary(snapshot: DatasetSnapshot) -> dict:
    return {
        "status": snapshot.status,
        "fetched_at": snapshot.fetched_at,
        "row_count": snapshot.row_count,
        "error": snapshot.error,
    }


def refresh_result(snapshot: DatasetSnapshot) -> dict:
    return {"source": snapshot.source, **snapshot_summary(snapshot)}


@router.get("")
async def list_datasets(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = []
    for source, info in SOURCE_INFO.items():
        latest = await queries.latest_snapshot(db, source)
        result.append({"source": source, **info, "latest": snapshot_summary(latest) if latest else None})
    return result


@router.post("/refresh")
async def refresh_datasets(body: RefreshRequest | None = None, db: AsyncSession = Depends(get_db)) -> list[dict]:
    snapshots = await refresh_all(db, body.sources if body else None)
    return [refresh_result(s) for s in snapshots]


@router.get("/fuel-prices")
async def get_fuel_prices(
    days: int = Query(90, ge=1, le=MAX_DAYS), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    return [{"date": p.price_date, "usd_per_gallon": p.usd_per_gallon} for p in await queries.fuel_prices(db, days)]


@router.get("/brent-prices")
async def get_brent_prices(
    days: int = Query(90, ge=1, le=MAX_DAYS), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Brent crude spot prices, oldest first, as [{"date": "YYYY-MM-DD", "usd_per_barrel": float}]."""
    return [{"date": p.price_date, "usd_per_barrel": p.usd_per_barrel} for p in await queries.brent_prices(db, days)]


@router.get("/fx-rates")
async def get_fx_rates(
    quote: str = Query("INR", min_length=3, max_length=3),
    days: int = Query(90, ge=1, le=MAX_DAYS),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return [{"date": r.rate_date, "rate": r.rate} for r in await queries.fx_rates(db, quote, days)]


@router.get("/market-routes")
async def get_market_routes(
    origin: str | None = Query(None, max_length=4),
    destination: str | None = Query(None, max_length=4),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return [
        {
            "airline_code": m.airline_code,
            "airline_name": m.airline_name,
            "origin": m.origin,
            "destination": m.destination,
            "stops": m.stops,
            "equipment": m.equipment,
        }
        for m in await queries.market_routes(db, origin, destination)
    ]


@router.get("/weather")
async def get_weather(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Latest observation and 7-day forecast for each twin airport."""
    result = []
    for airport, data in (await queries.weather_by_airport(db)).items():
        o, taf = data["observation"], data["taf"]
        result.append(
            {
                "airport": airport,
                "icao": AIRPORT_STATIONS[airport][0],
                "observed_at": o.observed_at if o else None,
                "flight_category": o.flight_category if o else "UNKNOWN",
                "wind_kt": o.wind_kt if o else None,
                "gust_kt": o.gust_kt if o else None,
                "visibility_sm": o.visibility_sm if o else None,
                "ceiling_ft": o.ceiling_ft if o else None,
                "raw_text": o.raw_text if o else None,
                "taf_worst_flight_category_24h": taf.worst_flight_category_24h if taf else None,
                "taf_thunderstorm_24h": taf.thunderstorm_24h if taf else None,
                "forecast": [
                    {
                        "date": f.forecast_date,
                        "precipitation_mm": f.precipitation_mm,
                        "max_gust_kmh": f.max_gust_kmh,
                        "weather_code": f.weather_code,
                        "thunderstorm": f.thunderstorm,
                    }
                    for f in data["forecast"]
                ],
            }
        )
    return result


@router.get("/airworthiness-directives")
async def get_airworthiness_directives(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """FAA airworthiness directives of the last 365 days that concern the twin's aircraft types, newest first."""
    return [
        {
            "document_number": ad.document_number,
            "title": ad.title,
            "publication_date": ad.publication_date,
            "html_url": ad.html_url,
            "aircraft_types": list(ad.aircraft_types),
        }
        for ad in await queries.airworthiness_directives(db)
    ]


@router.get("/dgca-traffic")
async def get_dgca_traffic(db: AsyncSession = Depends(get_db)) -> list[dict]:
    return [
        {
            "period": t.period,
            "airline": t.airline,
            "passengers": t.passengers,
            "market_share_pct": t.market_share_pct,
            "load_factor_pct": t.load_factor_pct,
            "is_fallback": t.is_fallback,
        }
        for t in await queries.dgca_traffic(db)
    ]


@router.get("/world-bank")
async def get_world_bank(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Latest non-null year of each World Bank indicator for India, in a fixed indicator order."""
    latest = await world_bank_latest(db)
    return [
        {"indicator": code, "label": label, "unit": unit, **latest[code]}
        for code, (label, unit) in INDICATORS.items()
        if code in latest
    ]


@router.get("/air-traffic/live")
async def get_air_traffic_live(db: AsyncSession = Depends(get_db)) -> dict:
    """Latest OpenSky snapshot: India totals and, per major airport, nearby aircraft and live congestion."""
    data = await latest_air_traffic(db)
    return data or {"taken_at": None, "india": None, "airports": []}


@router.get("/air-traffic/history")
async def get_air_traffic_history(
    airport: str | None = Query(None, min_length=3, max_length=3),
    limit: int = Query(48, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Newest-first stored snapshots of one airport (IATA code), or the India totals when no airport is given."""
    if airport is not None:
        airport = airport.upper()
        if airport not in AIRPORTS_BY_IATA:
            raise HTTPException(status_code=422, detail=f"unknown airport {airport}")
    return await air_traffic_history(db, airport, limit)


MAX_PAGE = 500


def _runway_row(r) -> dict:
    return {
        "designator": "/".join(end for end in (r.le_ident, r.he_ident) if end),
        "length_ft": r.length_ft,
        "width_ft": r.width_ft,
        "surface": r.surface,
        "lighted": r.lighted,
        "closed": r.closed,
    }


def _india_airport_row(airport, runways) -> dict:
    lengths = [r.length_ft for r in runways if r.length_ft is not None and not r.closed]
    return {
        "ident": airport.ident,
        "icao": airport.icao_code,
        "iata": airport.iata_code,
        "name": airport.name,
        "type": airport.airport_type,
        "city": airport.municipality,
        "latitude": airport.latitude_deg,
        "longitude": airport.longitude_deg,
        "elevation_ft": airport.elevation_ft,
        "scheduled_service": airport.scheduled_service,
        "frequency_count": airport.frequency_count,
        "runway_count": len(runways),
        "longest_runway_ft": max(lengths) if lengths else None,
        "runways": [_runway_row(r) for r in runways],
    }


@router.get("/india-airports")
async def get_india_airports(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Indian aerodromes (OurAirports), paged. `q` searches ident, ICAO/IATA code, name and city."""
    total, page = await queries.india_airports(db, q, limit, offset)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_india_airport_row(airport, runways) for airport, runways in page],
    }


@router.get("/airport-traffic")
async def get_airport_traffic(
    airport: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Monthly AAI traffic per airport, newest month first. `airport` is an IATA/ICAO code or part of the name."""
    total, rows = await queries.airport_traffic(db, airport, limit, offset)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "airport_name": t.airport_name,
                "iata": t.iata_code,
                "icao": t.icao_code,
                "period": t.period,
                "aircraft_movements": t.aircraft_movements,
                "passengers": t.passengers,
                "freight_tonnes": t.freight_tonnes,
                "movements_domestic": t.movements_domestic,
                "movements_international": t.movements_international,
                "passengers_domestic": t.passengers_domestic,
                "passengers_international": t.passengers_international,
                "freight_domestic_tonnes": t.freight_domestic_tonnes,
                "freight_international_tonnes": t.freight_international_tonnes,
                "movements_yoy_pct": t.movements_yoy_pct,
                "passengers_yoy_pct": t.passengers_yoy_pct,
                "freight_yoy_pct": t.freight_yoy_pct,
            }
            for t in rows
        ],
    }

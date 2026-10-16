"""Read-side queries over the normalised dataset tables (shared by the API and the evidence providers)."""
from datetime import date, timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.weather import AIRPORT_STATIONS, OPEN_METEO_SOURCE
from app.models.external import (
    SNAPSHOT_SUCCESS, AirportTrafficMonthly, AirworthinessDirective, DatasetSnapshot, IndiaAirport, IndiaRunway, DgcaTraffic, FuelPrice, FxRate, MarketRoute, OilPrice,
    WeatherForecast, WeatherObservation, WeatherTaf,
)

AD_WINDOW_DAYS = 365


async def airworthiness_directives(
    db: AsyncSession, aircraft_type: str | None = None, today: date | None = None
) -> list[AirworthinessDirective]:
    """ADs published in the last 365 days (newest first), optionally only those concerning `aircraft_type`."""
    since = (today or date.today()) - timedelta(days=AD_WINDOW_DAYS)
    stmt = select(AirworthinessDirective).where(AirworthinessDirective.publication_date >= since)
    if aircraft_type is not None:
        stmt = stmt.where(AirworthinessDirective.aircraft_types.contains([aircraft_type]))
    stmt = stmt.order_by(AirworthinessDirective.publication_date.desc(), AirworthinessDirective.document_number.desc())
    return list((await db.execute(stmt)).scalars().all())


async def latest_snapshot(db: AsyncSession, source: str, *, status: str | None = None) -> DatasetSnapshot | None:
    stmt = select(DatasetSnapshot).where(DatasetSnapshot.source == source)
    if status is not None:
        stmt = stmt.where(DatasetSnapshot.status == status)
    stmt = stmt.order_by(DatasetSnapshot.fetched_at.desc(), DatasetSnapshot.created_at.desc()).limit(1)
    return (await db.execute(stmt)).scalars().first()


async def fuel_prices(db: AsyncSession, days: int, today: date | None = None) -> list[FuelPrice]:
    """Prices from the last `days` days (ascending by date)."""
    since = (today or date.today()) - timedelta(days=days)
    stmt = select(FuelPrice).where(FuelPrice.price_date >= since).order_by(FuelPrice.price_date)
    return list((await db.execute(stmt)).scalars().all())


async def brent_prices(db: AsyncSession, days: int, today: date | None = None) -> list[OilPrice]:
    """Brent prices from the last `days` days (ascending by date)."""
    since = (today or date.today()) - timedelta(days=days)
    stmt = select(OilPrice).where(OilPrice.price_date >= since).order_by(OilPrice.price_date)
    return list((await db.execute(stmt)).scalars().all())


async def fx_rates(db: AsyncSession, quote: str, days: int, today: date | None = None) -> list[FxRate]:
    since = (today or date.today()) - timedelta(days=days)
    stmt = (
        select(FxRate)
        .where(FxRate.quote == quote.upper(), FxRate.rate_date >= since)
        .order_by(FxRate.rate_date)
    )
    return list((await db.execute(stmt)).scalars().all())


async def market_routes(db: AsyncSession, origin: str | None = None, destination: str | None = None) -> list[MarketRoute]:
    stmt = select(MarketRoute)
    if origin:
        stmt = stmt.where(MarketRoute.origin == origin.upper())
    if destination:
        stmt = stmt.where(MarketRoute.destination == destination.upper())
    stmt = stmt.order_by(MarketRoute.origin, MarketRoute.destination, MarketRoute.airline_name, MarketRoute.airline_code)
    return list((await db.execute(stmt)).scalars().all())


async def dgca_traffic(db: AsyncSession) -> list[DgcaTraffic]:
    """All rows, latest period first, biggest market share first within a period."""
    stmt = select(DgcaTraffic).order_by(
        DgcaTraffic.period.desc(), DgcaTraffic.market_share_pct.desc().nulls_last(), DgcaTraffic.airline
    )
    return list((await db.execute(stmt)).scalars().all())


async def latest_dgca_period(db: AsyncSession) -> str | None:
    return (await db.execute(select(func.max(DgcaTraffic.period)))).scalar_one_or_none()


async def weather_by_airport(db: AsyncSession) -> dict[str, dict]:
    """For each twin airport (twin order): its latest observation (or None), its latest TAF (or None) and the
    forecast days of the latest successful Open-Meteo snapshot (ascending by date; empty when there is no such snapshot)."""
    return await weather_for_airports(db, list(AIRPORT_STATIONS))


async def weather_for_airports(db: AsyncSession, airports: list[str]) -> dict[str, dict]:
    """`weather_by_airport` for any list of (IATA) airport codes, in that order."""
    newest = (
        select(WeatherObservation.airport, func.max(WeatherObservation.observed_at).label("observed_at"))
        .where(WeatherObservation.airport.in_(airports))
        .group_by(WeatherObservation.airport)
        .subquery()
    )
    observed = (
        await db.execute(
            select(WeatherObservation).join(
                newest,
                (WeatherObservation.airport == newest.c.airport) & (WeatherObservation.observed_at == newest.c.observed_at),
            )
        )
    ).scalars().all()
    observation_by_airport = {o.airport: o for o in observed}
    tafs = (
        await db.execute(
            select(WeatherTaf).where(WeatherTaf.airport.in_(airports)).order_by(WeatherTaf.airport, WeatherTaf.issued_at)
        )
    ).scalars().all()
    taf_by_airport = {t.airport: t for t in tafs}  # ascending, so the newest issue of an airport wins
    forecasts: dict[str, list[WeatherForecast]] = {}
    snapshot = await latest_snapshot(db, OPEN_METEO_SOURCE, status=SNAPSHOT_SUCCESS)
    if snapshot is not None:
        rows = (
            await db.execute(
                select(WeatherForecast)
                .where(WeatherForecast.snapshot_id == snapshot.id, WeatherForecast.airport.in_(airports))
                .order_by(WeatherForecast.airport, WeatherForecast.forecast_date)
            )
        ).scalars().all()
        for row in rows:
            forecasts.setdefault(row.airport, []).append(row)
    return {
        airport: {
            "observation": observation_by_airport.get(airport),
            "taf": taf_by_airport.get(airport),
            "forecast": forecasts.get(airport, []),
        }
        for airport in airports
    }


_TYPE_RANK = case(
    (IndiaAirport.airport_type == "large_airport", 0),
    (IndiaAirport.airport_type == "medium_airport", 1),
    (IndiaAirport.airport_type == "small_airport", 2),
    else_=3,
)


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def india_airports(
    db: AsyncSession, q: str | None = None, limit: int = 50, offset: int = 0
) -> tuple[int, list[tuple[IndiaAirport, list[IndiaRunway]]]]:
    """(total matches, page) of Indian aerodromes, scheduled-service and bigger airports first.

    `q` matches the ident, ICAO, IATA, name or city (case-insensitive substring). Each airport comes with its runways.
    """
    stmt = select(IndiaAirport)
    q = (q or "").strip()
    if q:
        pattern = _like(q)
        stmt = stmt.where(
            or_(
                IndiaAirport.ident.ilike(pattern, escape="\\"),
                IndiaAirport.icao_code.ilike(pattern, escape="\\"),
                IndiaAirport.iata_code.ilike(pattern, escape="\\"),
                IndiaAirport.name.ilike(pattern, escape="\\"),
                IndiaAirport.municipality.ilike(pattern, escape="\\"),
            )
        )
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(IndiaAirport.scheduled_service.desc(), _TYPE_RANK, IndiaAirport.name, IndiaAirport.ident)
    airports = list((await db.execute(stmt.limit(limit).offset(offset))).scalars().all())
    runways = await runways_by_ident(db, [a.ident for a in airports])
    return total, [(a, runways.get(a.ident, [])) for a in airports]


async def runways_by_ident(db: AsyncSession, idents: list[str]) -> dict[str, list[IndiaRunway]]:
    if not idents:
        return {}
    rows = (
        await db.execute(
            select(IndiaRunway)
            .where(IndiaRunway.airport_ident.in_(idents))
            .order_by(IndiaRunway.airport_ident, IndiaRunway.length_ft.desc().nulls_last(), IndiaRunway.ourairports_id)
        )
    ).scalars().all()
    result: dict[str, list[IndiaRunway]] = {}
    for row in rows:
        result.setdefault(row.airport_ident, []).append(row)
    return result


async def india_airport_by_code(db: AsyncSession, code: str) -> tuple[IndiaAirport, list[IndiaRunway]] | None:
    """The airport with this IATA or ICAO/ident code (scheduled service first) with its runways, or None."""
    code = code.strip().upper()
    stmt = (
        select(IndiaAirport)
        .where(or_(IndiaAirport.iata_code == code, IndiaAirport.icao_code == code, IndiaAirport.ident == code))
        .order_by(IndiaAirport.scheduled_service.desc(), _TYPE_RANK, IndiaAirport.ident)
        .limit(1)
    )
    airport = (await db.execute(stmt)).scalars().first()
    if airport is None:
        return None
    return airport, (await runways_by_ident(db, [airport.ident])).get(airport.ident, [])


async def airport_traffic(
    db: AsyncSession, airport: str | None = None, limit: int = 50, offset: int = 0
) -> tuple[int, list[AirportTrafficMonthly]]:
    """(total, page) of monthly traffic rows, newest month first and busiest airport first.

    `airport` matches the IATA/ICAO code or part of the published airport name (case-insensitive).
    """
    stmt = select(AirportTrafficMonthly)
    airport = (airport or "").strip()
    if airport:
        pattern = _like(airport)
        stmt = stmt.where(
            or_(
                AirportTrafficMonthly.iata_code == airport.upper(),
                AirportTrafficMonthly.icao_code == airport.upper(),
                AirportTrafficMonthly.airport_name.ilike(pattern, escape="\\"),
            )
        )
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(
        AirportTrafficMonthly.period.desc(),
        AirportTrafficMonthly.passengers.desc().nulls_last(),
        AirportTrafficMonthly.airport_name,
    )
    return total, list((await db.execute(stmt.limit(limit).offset(offset))).scalars().all())


async def latest_airport_traffic(db: AsyncSession, code: str) -> AirportTrafficMonthly | None:
    """The newest monthly traffic row of the airport with this IATA or ICAO code."""
    code = code.strip().upper()
    stmt = (
        select(AirportTrafficMonthly)
        .where(or_(AirportTrafficMonthly.iata_code == code, AirportTrafficMonthly.icao_code == code))
        .order_by(AirportTrafficMonthly.period.desc(), AirportTrafficMonthly.passengers.desc().nulls_last())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()

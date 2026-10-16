"""Evidence providers backed by the downloaded datasets. Each returns [] when its table is empty."""
from datetime import date, timedelta, timezone
from statistics import mean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import eia, fx, openflights, queries, weather
from app.datasets.queries import latest_dgca_period, latest_snapshot
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.reliability import SOURCE_RELIABILITY
from app.models.digital_twin import Airport, Route
from app.models.external import SNAPSHOT_SUCCESS, DgcaTraffic, FuelPrice, FxRate, MarketRoute

TOP_AIRLINES = 5


def parse_route(route: str | None) -> tuple[str, str] | None:
    """'BOM-DEL' -> ('BOM', 'DEL'); None for anything else."""
    if not route:
        return None
    parts = route.strip().upper().split("-")
    if len(parts) != 2 or not all(parts):
        return None
    return parts[0], parts[1]


def pct_change(latest: float, earlier: float | None) -> float | None:
    if earlier is None or earlier == 0:
        return None
    return round((latest / earlier - 1) * 100, 2)


async def _twin_route_pairs(db: AsyncSession) -> list[tuple[str, str]]:
    origin, destination = Airport.__table__.alias("o"), Airport.__table__.alias("d")
    stmt = (
        select(origin.c.code, destination.c.code)
        .select_from(Route.__table__.join(origin, Route.origin_id == origin.c.id).join(destination, Route.destination_id == destination.c.id))
        .order_by(origin.c.code, destination.c.code)
    )
    return [(o, d) for o, d in (await db.execute(stmt)).all()]


async def market_competition(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """Rival airlines (OpenFlights) on the request's route, or on each twin route when there is none."""
    parsed = parse_route(request.route)
    pairs = [parsed] if parsed else await _twin_route_pairs(db)
    if not pairs:
        return []
    snapshot = await latest_snapshot(db, openflights.SOURCE, status=SNAPSHOT_SUCCESS)
    items: list[EvidenceItem] = []
    for origin, destination in pairs:
        rows = (
            await db.execute(
                select(MarketRoute)
                .where(MarketRoute.origin == origin, MarketRoute.destination == destination)
                .order_by(MarketRoute.airline_name, MarketRoute.airline_code)
            )
        ).scalars().all()
        if not rows:
            continue
        airlines = [
            {"code": r.airline_code, "name": r.airline_name, "stops": r.stops, "equipment": r.equipment} for r in rows
        ]
        items.append(
            EvidenceItem(
                id=f"market:{origin}-{destination}",
                source="openflights",
                kind="dataset",
                title=f"Airlines operating {origin}-{destination} (OpenFlights)",
                url=openflights.ROUTES_URL,
                fetched_at=snapshot.fetched_at if snapshot else None,
                reliability=SOURCE_RELIABILITY["openflights"],
                content={"route": f"{origin}-{destination}", "rival_count": len(airlines), "airlines": airlines},
            )
        )
    return items


async def fuel_price(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """Latest EIA jet fuel price with its 30- and 90-day averages and the change over 30 days."""
    latest = (await db.execute(select(FuelPrice).order_by(FuelPrice.price_date.desc()).limit(1))).scalars().first()
    if latest is None:
        return []

    async def prices_since(days: int) -> list[float]:
        since = latest.price_date - timedelta(days=days)
        stmt = select(FuelPrice.usd_per_gallon).where(FuelPrice.series == latest.series, FuelPrice.price_date >= since)
        return list((await db.execute(stmt)).scalars().all())

    async def price_on_or_before(day: date) -> float | None:
        stmt = (
            select(FuelPrice.usd_per_gallon)
            .where(FuelPrice.series == latest.series, FuelPrice.price_date <= day)
            .order_by(FuelPrice.price_date.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    last_30, last_90 = await prices_since(30), await prices_since(90)
    month_ago = await price_on_or_before(latest.price_date - timedelta(days=30))
    return [
        EvidenceItem(
            id=f"fuel:eia:{latest.price_date.isoformat()}",
            source="eia_jet_fuel",
            kind="dataset",
            title="U.S. Gulf Coast jet fuel spot price (EIA)",
            url=eia.URL,
            fetched_at=latest.updated_at,
            reliability=SOURCE_RELIABILITY["eia_jet_fuel"],
            content={
                "series": latest.series,
                "latest_date": latest.price_date.isoformat(),
                "latest_usd_per_gallon": latest.usd_per_gallon,
                "avg_30d_usd_per_gallon": round(mean(last_30), 4),
                "avg_90d_usd_per_gallon": round(mean(last_90), 4),
                "change_pct_vs_30d_ago": pct_change(latest.usd_per_gallon, month_ago),
            },
        )
    ]


async def fx_rate(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """Latest USD/INR and its change over 30 days."""
    latest = (
        await db.execute(
            select(FxRate).where(FxRate.base == fx.BASE, FxRate.quote == fx.QUOTE).order_by(FxRate.rate_date.desc()).limit(1)
        )
    ).scalars().first()
    if latest is None:
        return []
    stmt = (
        select(FxRate.rate)
        .where(FxRate.base == fx.BASE, FxRate.quote == fx.QUOTE, FxRate.rate_date <= latest.rate_date - timedelta(days=30))
        .order_by(FxRate.rate_date.desc())
        .limit(1)
    )
    month_ago = (await db.execute(stmt)).scalar_one_or_none()
    return [
        EvidenceItem(
            id=f"fx:usd_inr:{latest.rate_date.isoformat()}",
            source="fx",
            kind="dataset",
            title="USD to INR exchange rate (ECB via Frankfurter)",
            url=fx.API_ROOT,
            fetched_at=latest.updated_at,
            reliability=SOURCE_RELIABILITY["fx"],
            content={
                "latest_date": latest.rate_date.isoformat(),
                "usd_inr": latest.rate,
                "change_pct_vs_30d_ago": pct_change(latest.rate, month_ago),
            },
        )
    ]


def _weather_airports(request: EvidenceRequest) -> list[str]:
    """The route's twin airports that have weather stations, or every station when there is no usable route."""
    parsed = parse_route(request.route)
    if parsed is None:
        return list(weather.AIRPORT_STATIONS)
    return [code for code in dict.fromkeys(parsed) if code in weather.AIRPORT_STATIONS]


async def weather_observation(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """The latest METAR of each airport on the request's route (all airports when there is no route)."""
    airports = _weather_airports(request)
    by_airport = await queries.weather_by_airport(db)
    items = []
    for airport in airports:
        o = by_airport[airport]["observation"]
        if o is None:
            continue
        items.append(
            EvidenceItem(
                id=f"metar:{airport}:{o.observed_at.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}",
                source="aviation_weather",
                kind="dataset",
                title=f"Current weather at {airport} ({o.icao} METAR)",
                url=weather.metar_url(),
                fetched_at=o.updated_at,
                reliability=SOURCE_RELIABILITY["aviation_weather"],
                content={
                    "airport": airport,
                    "icao": o.icao,
                    "observed_at": o.observed_at.isoformat(),
                    "flight_category": o.flight_category,
                    "wind_kt": o.wind_kt,
                    "gust_kt": o.gust_kt,
                    "visibility_sm": o.visibility_sm,
                    "ceiling_ft": o.ceiling_ft,
                    "raw_text": o.raw_text,
                },
            )
        )
    return items


async def weather_forecast(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """The 7-day forecast of each airport on the request's route (all airports when there is no route)."""
    airports = _weather_airports(request)
    by_airport = await queries.weather_by_airport(db)
    items = []
    for airport in airports:
        days = by_airport[airport]["forecast"]
        if not days:
            continue
        items.append(
            EvidenceItem(
                id=f"forecast:{airport}:{days[0].forecast_date.isoformat()}",
                source="open_meteo",
                kind="dataset",
                title=f"7-day weather forecast for {airport} (Open-Meteo)",
                url=weather.forecast_url(),
                fetched_at=max(d.updated_at for d in days),
                reliability=SOURCE_RELIABILITY["open_meteo"],
                content={
                    "airport": airport,
                    "thunderstorm_days": sum(1 for d in days if d.thunderstorm),
                    "disruption_days": sum(
                        1 for d in days if weather.is_disruptive_day(d.precipitation_mm, d.max_gust_kmh, d.thunderstorm)
                    ),
                    "max_precipitation_mm": max(d.precipitation_mm for d in days),
                    "max_gust_kmh": max(d.max_gust_kmh for d in days),
                    "days": [
                        {
                            "date": d.forecast_date.isoformat(),
                            "precipitation_mm": d.precipitation_mm,
                            "max_gust_kmh": d.max_gust_kmh,
                            "weather_code": d.weather_code,
                            "thunderstorm": d.thunderstorm,
                        }
                        for d in days
                    ],
                },
            )
        )
    return items


async def dgca_market(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """Top airlines by market share in the latest DGCA period, and the average load factor."""
    period = await latest_dgca_period(db)
    if period is None:
        return []
    rows = (
        await db.execute(
            select(DgcaTraffic)
            .where(DgcaTraffic.period == period)
            .order_by(DgcaTraffic.market_share_pct.desc().nulls_last(), DgcaTraffic.airline)
        )
    ).scalars().all()
    load_factors = [r.load_factor_pct for r in rows if r.load_factor_pct is not None]
    return [
        EvidenceItem(
            id=f"dgca:{period}",
            source="dgca",
            kind="dataset",
            title=f"DGCA domestic traffic, {period}",
            url=rows[0].source_url,
            fetched_at=max(r.updated_at for r in rows),
            reliability=SOURCE_RELIABILITY["dgca"],
            content={
                "period": period,
                "is_fallback": any(r.is_fallback for r in rows),
                "top_airlines": [
                    {
                        "airline": r.airline,
                        "passengers": r.passengers,
                        "market_share_pct": r.market_share_pct,
                        "load_factor_pct": r.load_factor_pct,
                    }
                    for r in rows[:TOP_AIRLINES]
                ],
                # Simple average over the airlines that report a load factor (not passenger-weighted).
                "industry_avg_load_factor_pct": round(mean(load_factors), 2) if load_factors else None,
            },
        )
    ]

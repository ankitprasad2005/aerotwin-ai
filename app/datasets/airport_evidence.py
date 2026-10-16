"""Evidence providers for the route's two airports: OurAirports infrastructure and AAI monthly throughput."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import aai_traffic, ourairports, queries
from app.datasets.evidence import parse_route
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.reliability import SOURCE_RELIABILITY
from app.models.external import SNAPSHOT_SUCCESS, IndiaRunway

FEET_PER_METRE = 3.28084


def _runway_summary(runway: IndiaRunway) -> dict:
    return {
        "designator": "/".join(end for end in (runway.le_ident, runway.he_ident) if end),
        "length_ft": runway.length_ft,
        "width_ft": runway.width_ft,
        "surface": runway.surface,
        "lighted": runway.lighted,
        "closed": runway.closed,
    }


async def airport_infrastructure(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """Runways, longest runway and elevation of the route's two airports (OurAirports). [] without a route."""
    codes = parse_route(request.route)
    if codes is None:
        return []
    snapshot = await queries.latest_snapshot(db, ourairports.SOURCE, status=SNAPSHOT_SUCCESS)
    items = []
    for code in codes:
        found = await queries.india_airport_by_code(db, code)
        if found is None:
            continue
        airport, runways = found
        open_runways = [r for r in runways if not r.closed]
        lengths = [r.length_ft for r in open_runways if r.length_ft is not None]
        longest = max(lengths) if lengths else None
        items.append(
            EvidenceItem(
                id=f"ourairports:{code}",
                source="ourairports",
                kind="dataset",
                title=f"{code} airport infrastructure: {len(open_runways)} runway(s) (OurAirports)",
                url=f"https://ourairports.com/airports/{airport.ident}/",
                fetched_at=snapshot.fetched_at if snapshot else None,
                reliability=SOURCE_RELIABILITY["ourairports"],
                content={
                    "airport": code,
                    "icao": airport.icao_code,
                    "name": airport.name,
                    "city": airport.municipality,
                    "elevation_ft": airport.elevation_ft,
                    "runway_count": len(runways),
                    "open_runway_count": len(open_runways),
                    "longest_runway_ft": longest,
                    "longest_runway_m": round(longest / FEET_PER_METRE) if longest is not None else None,
                    "frequency_count": airport.frequency_count,
                    "runways": [_runway_summary(r) for r in runways],
                },
            )
        )
    return items


async def airport_throughput(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """Latest monthly movements, passengers, freight and year-on-year change of the route's two airports (AAI)."""
    codes = parse_route(request.route)
    if codes is None:
        return []
    snapshot = await queries.latest_snapshot(db, aai_traffic.SOURCE, status=SNAPSHOT_SUCCESS)
    items = []
    for code in codes:
        row = await queries.latest_airport_traffic(db, code)
        if row is None:
            continue
        items.append(
            EvidenceItem(
                id=f"aai:{code}:{row.period}",
                source="aai_traffic",
                kind="dataset",
                title=f"{code} airport traffic, {row.period} (AAI)",
                url=aai_traffic.INDEX_URL,
                fetched_at=snapshot.fetched_at if snapshot else None,
                reliability=SOURCE_RELIABILITY["aai_traffic"],
                content={
                    "airport": code,
                    "airport_name": row.airport_name,
                    "period": row.period,
                    "aircraft_movements": row.aircraft_movements,
                    "passengers": row.passengers,
                    "freight_tonnes": row.freight_tonnes,
                    "movements_domestic": row.movements_domestic,
                    "movements_international": row.movements_international,
                    "passengers_domestic": row.passengers_domestic,
                    "passengers_international": row.passengers_international,
                    "movements_yoy_pct": row.movements_yoy_pct,
                    "passengers_yoy_pct": row.passengers_yoy_pct,
                    "freight_yoy_pct": row.freight_yoy_pct,
                },
            )
        )
    return items

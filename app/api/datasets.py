from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.datasets import queries
from app.datasets.refresh import SOURCE_INFO, refresh_all, validate_sources
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

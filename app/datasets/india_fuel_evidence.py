"""Evidence providers for the Indian fuel prices: Indian Oil ATF at the route origin's metro and the PPAC crude basket."""
from datetime import date
from statistics import mean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import india_fuel, iocl_atf, ppac_crude
from app.datasets.evidence import parse_route, pct_change
from app.datasets.queries import latest_snapshot
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.reliability import SOURCE_RELIABILITY
from app.models.external import SNAPSHOT_SUCCESS, IndianCrudeBasket


def _today() -> date:
    return date.today()


async def atf_india(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """ATF price at the route origin's metro (nearest metro, else Delhi, for other airports) and its changes."""
    parsed = parse_route(request.route)
    origin = parsed[0] if parsed else None
    metro, match = india_fuel.metro_for_airport(origin or "")
    month = india_fuel.month_start(_today())
    current = await india_fuel.atf_in_effect(db, metro, month)
    if current is None:
        return []
    previous = await india_fuel.atf_before(db, metro, current.price_month)
    year_ago = await india_fuel.atf_in_effect(db, metro, india_fuel.add_months(current.price_month, -12))
    international = await india_fuel.atf_in_effect(db, metro, month, iocl_atf.INTERNATIONAL)
    snapshot = await latest_snapshot(db, iocl_atf.SOURCE, status=SNAPSHOT_SUCCESS)

    def change(other):
        return pct_change(current.inr_per_kl, other.inr_per_kl) if other is not None else None

    return [
        EvidenceItem(
            id=f"atf:iocl:{metro}:{current.price_month.isoformat()}",
            source="iocl",
            kind="dataset",
            title=f"Indian Oil ATF price at {metro} (INR per kilolitre, domestic airlines)",
            url=iocl_atf.PAGE_URL,
            fetched_at=snapshot.fetched_at if snapshot else None,
            reliability=SOURCE_RELIABILITY["iocl"],
            content={
                "city": metro,
                "origin_airport": origin,
                "city_match": match if origin else "default_delhi",
                "price_month": current.price_month.isoformat(),
                "inr_per_kl": current.inr_per_kl,
                "international_run_usd_per_kl": international.usd_per_kl if international else None,
                "previous_price_month": previous.price_month.isoformat() if previous else None,
                "change_pct_vs_previous_month": change(previous),
                "year_ago_price_month": year_ago.price_month.isoformat() if year_ago else None,
                "change_pct_vs_year_ago": change(year_ago),
                "note": "A price stays in effect until Indian Oil revises it; changes compare with the previous "
                "published revision and with the price in effect twelve months earlier.",
                "data_via": (snapshot.details or {}).get("via") if snapshot else None,
            },
        )
    ]


async def crude_basket_india(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """Latest PPAC Indian crude basket month (USD/bbl), its 3-month average and changes."""
    latest = (
        await db.execute(select(IndianCrudeBasket).order_by(IndianCrudeBasket.price_month.desc()).limit(1))
    ).scalars().first()
    if latest is None:
        return []

    async def on(month: date) -> float | None:
        stmt = select(IndianCrudeBasket.usd_per_bbl).where(IndianCrudeBasket.price_month == month)
        return (await db.execute(stmt)).scalar_one_or_none()

    last_three = [
        v for v in [await on(india_fuel.add_months(latest.price_month, -i)) for i in range(3)] if v is not None
    ]
    snapshot = await latest_snapshot(db, ppac_crude.SOURCE, status=SNAPSHOT_SUCCESS)
    previous = await on(india_fuel.add_months(latest.price_month, -1))
    year_ago = await on(india_fuel.add_months(latest.price_month, -12))
    return [
        EvidenceItem(
            id=f"crude:ppac:{latest.price_month.isoformat()}",
            source="ppac",
            kind="dataset",
            title="Indian crude oil basket price (PPAC, USD per barrel)",
            url=ppac_crude.PAGE_URL,
            fetched_at=snapshot.fetched_at if snapshot else None,
            reliability=SOURCE_RELIABILITY["ppac"],
            content={
                "price_month": latest.price_month.isoformat(),
                "usd_per_bbl": latest.usd_per_bbl,
                "avg_3m_usd_per_bbl": round(mean(last_three), 2),
                "change_pct_vs_previous_month": pct_change(latest.usd_per_bbl, previous),
                "change_pct_vs_year_ago": pct_change(latest.usd_per_bbl, year_ago),
                "note": "The latest month is a month-to-date average.",
            },
        )
    ]

"""Evidence providers for the market, network and cargo agents: World Bank indicators and Indian holidays."""
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import world_bank
from app.datasets.india_holidays import PACKAGE_URL, SOURCE as HOLIDAYS_SOURCE, WINDOW_WEEKS, upcoming_holidays
from app.datasets.queries import latest_snapshot
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.reliability import SOURCE_RELIABILITY
from app.models.external import SNAPSHOT_SUCCESS


def _today() -> date:
    return date.today()


async def _indicator_items(db: AsyncSession, codes: tuple[str, ...]) -> list[EvidenceItem]:
    latest = await world_bank.world_bank_latest(db)
    snapshot = await latest_snapshot(db, world_bank.SOURCE, status=SNAPSHOT_SUCCESS)
    items = []
    for code in codes:
        if code not in latest:
            continue
        label, unit = world_bank.INDICATORS[code]
        data = latest[code]
        items.append(
            EvidenceItem(
                id=f"worldbank:{code}:{data['year']}",
                source="world_bank",
                kind="dataset",
                title=f"India {label.lower()}, {data['year']} (World Bank)",
                url=world_bank.indicator_url(code),
                fetched_at=snapshot.fetched_at if snapshot else None,
                reliability=SOURCE_RELIABILITY["world_bank"],
                content={"indicator": code, "label": label, "unit": unit, **data},
            )
        )
    return items


async def world_bank_demand(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """India's latest air passengers carried and GDP growth (World Bank)."""
    return await _indicator_items(db, (world_bank.PASSENGERS, world_bank.GDP_GROWTH))


async def world_bank_freight(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """India's latest air freight, million ton-km (World Bank)."""
    return await _indicator_items(db, (world_bank.FREIGHT,))


async def india_holidays(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """Indian public holidays in the next 8 weeks from today (offline `holidays` package)."""
    today = _today()
    found = upcoming_holidays(today)
    return [
        EvidenceItem(
            id=f"holidays:IN:{today.isoformat()}",
            source="india_holidays",
            kind="dataset",
            title=f"Indian public holidays, next {WINDOW_WEEKS} weeks",
            url=PACKAGE_URL,
            fetched_at=datetime.now(timezone.utc),
            reliability=SOURCE_RELIABILITY[HOLIDAYS_SOURCE],
            content={"from": today.isoformat(), "weeks": WINDOW_WEEKS, "count": len(found), "holidays": found},
        )
    ]

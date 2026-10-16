from datetime import date, datetime, timezone

from app.datasets import market_evidence
from app.datasets.india_holidays import upcoming_holidays
from app.datasets.market_evidence import india_holidays, world_bank_demand, world_bank_freight
from app.evidence.base import EvidenceRequest
from app.models.external import SNAPSHOT_SUCCESS, DatasetSnapshot, WorldBankIndicator


def _request():
    return EvidenceRequest(agent_type="MARKET", objective="x", route="BOM-DEL", previous_results=[])


def test_upcoming_holidays_window_is_sorted_and_ends_after_eight_weeks():
    # 2026-10-16 + 8 weeks = 2026-12-11, so Christmas is outside the window.
    assert upcoming_holidays(date(2026, 10, 16)) == [
        {"date": "2026-10-20", "name": "Dussehra"},
        {"date": "2026-11-08", "name": "Diwali (Deepavali)"},
        {"date": "2026-11-24", "name": "Guru Nanak's Jayanti"},
    ]


def test_upcoming_holidays_includes_both_ends_of_the_window():
    assert [h["date"] for h in upcoming_holidays(date(2026, 10, 20), weeks=0)] == ["2026-10-20"]


def test_upcoming_holidays_spans_the_new_year():
    found = upcoming_holidays(date(2026, 12, 20))
    assert [h["date"] for h in found][:2] == ["2026-12-25", "2027-01-26"]


async def test_providers_return_nothing_without_world_bank_data(db_session):
    assert await world_bank_demand(db_session, _request()) == []
    assert await world_bank_freight(db_session, _request()) == []


async def test_world_bank_providers_split_the_indicators(db_session):
    fetched = datetime(2026, 10, 11, tzinfo=timezone.utc)
    db_session.add(DatasetSnapshot(source="world_bank", fetched_at=fetched, status=SNAPSHOT_SUCCESS, source_url="https://x"))
    db_session.add_all([
        WorldBankIndicator(indicator="IS.AIR.PSGR", year=2022, value=100.0),
        WorldBankIndicator(indicator="IS.AIR.PSGR", year=2023, value=110.0),
        WorldBankIndicator(indicator="IS.AIR.GOOD.MT.K1", year=2023, value=1800.0),
        WorldBankIndicator(indicator="NY.GDP.MKTP.KD.ZG", year=2025, value=7.5),
    ])
    await db_session.flush()

    demand = await world_bank_demand(db_session, _request())
    freight = await world_bank_freight(db_session, _request())

    assert [i.id for i in demand] == ["worldbank:IS.AIR.PSGR:2023", "worldbank:NY.GDP.MKTP.KD.ZG:2025"]
    assert [i.id for i in freight] == ["worldbank:IS.AIR.GOOD.MT.K1:2023"]
    item = demand[0]
    assert item.source == "world_bank" and item.kind == "dataset" and item.reliability == 0.85
    assert item.fetched_at == fetched and item.url.endswith("IS.AIR.PSGR?format=json&per_page=20")
    assert item.content["yoy_pct"] == 10.0 and item.content["unit"] == "passengers"


async def test_world_bank_provider_without_snapshot_has_no_fetched_at(db_session):
    db_session.add(WorldBankIndicator(indicator="IS.AIR.GOOD.MT.K1", year=2023, value=1800.0))
    await db_session.flush()

    [item] = await world_bank_freight(db_session, _request())

    assert item.fetched_at is None


async def test_india_holidays_item(db_session, monkeypatch):
    monkeypatch.setattr(market_evidence, "_today", lambda: date(2026, 10, 16))

    [item] = await india_holidays(db_session, _request())

    assert item.id == "holidays:IN:2026-10-16" and item.source == "india_holidays" and item.reliability == 0.95
    assert item.content["count"] == 3 and len(item.content["holidays"]) == 3
    assert item.content["holidays"][0] == {"date": "2026-10-20", "name": "Dussehra"}
    assert item.content["weeks"] == 8

from pathlib import Path

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.datasets import router
from app.api.deps import get_db
from app.datasets import common, world_bank
from app.datasets.common import DatasetError
from app.datasets.world_bank import fetch_world_bank, parse_world_bank, world_bank_latest
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, WorldBankIndicator

FIXTURES = Path(__file__).parent / "fixtures" / "datasets"
PASSENGERS = (FIXTURES / "worldbank_ind_passengers.json").read_bytes()
FREIGHT = (FIXTURES / "worldbank_ind_freight.json").read_bytes()
GDP = (FIXTURES / "worldbank_ind_gdp_growth.json").read_bytes()


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


def _mock(passengers=PASSENGERS, freight=FREIGHT, gdp=GDP):
    respx.get(world_bank.indicator_url(world_bank.PASSENGERS)).mock(return_value=httpx.Response(200, content=passengers))
    respx.get(world_bank.indicator_url(world_bank.FREIGHT)).mock(return_value=httpx.Response(200, content=freight))
    respx.get(world_bank.indicator_url(world_bank.GDP_GROWTH)).mock(return_value=httpx.Response(200, content=gdp))


def test_indicator_url():
    assert world_bank.indicator_url("IS.AIR.PSGR") == (
        "https://api.worldbank.org/v2/country/IND/indicator/IS.AIR.PSGR?format=json&per_page=20"
    )


def test_parse_real_fixture_skips_null_years_and_sorts_ascending():
    parsed = parse_world_bank(PASSENGERS)
    assert [y for y, _ in parsed] == [2020, 2021, 2022, 2023]  # 2024 and 2025 are null in the real response
    assert parsed[-1] == (2023, 180415784.228)
    assert parse_world_bank(GDP)[-1] == (2025, 7.56666179284244)


def test_parse_skips_malformed_records():
    content = b'[{"page":1},[{"date":"x","value":1.0},{"date":"2020","value":"abc"},{"value":2.0},{"date":"2021","value":3}]]'
    assert parse_world_bank(content) == [(2021, 3.0)]


@pytest.mark.parametrize("junk", [b"", b"not json", b"[]", b'[{"page":1}]', b'[{}, {"a": 1}]', b'{"message": "error"}'])
def test_parse_rejects_malformed_payloads(junk):
    with pytest.raises(DatasetError, match="malformed"):
        parse_world_bank(junk)


@respx.mock
async def test_fetch_stores_rows_and_snapshot_and_is_idempotent(db_session, tmp_path):
    _mock()

    snapshot = await fetch_world_bank(db_session, base_dir=tmp_path)
    again = await fetch_world_bank(db_session, base_dir=tmp_path)

    assert snapshot.source == "world_bank" and snapshot.status == again.status == SNAPSHOT_SUCCESS
    assert snapshot.row_count == 14 and snapshot.details["latest_year"] == {
        "IS.AIR.PSGR": 2023, "IS.AIR.GOOD.MT.K1": 2023, "NY.GDP.MKTP.KD.ZG": 2025,
    }
    rows = (await db_session.execute(select(WorldBankIndicator))).scalars().all()
    assert len(rows) == 14 and all(r.snapshot_id == again.id for r in rows)
    assert len(list(tmp_path.rglob("*.json"))) == 3


@respx.mock
async def test_http_failure_records_a_failed_snapshot_and_no_rows(db_session, tmp_path):
    _mock()
    respx.get(world_bank.indicator_url(world_bank.FREIGHT)).mock(return_value=httpx.Response(500))

    snapshot = await fetch_world_bank(db_session, base_dir=tmp_path)

    assert snapshot.status == SNAPSHOT_FAILED and "download" in snapshot.error
    assert (await db_session.execute(select(WorldBankIndicator))).scalars().all() == []


@respx.mock
async def test_indicator_without_values_fails_rather_than_inventing(db_session, tmp_path):
    _mock(freight=b'[{"page":1},[{"date":"2024","value":null}]]')

    snapshot = await fetch_world_bank(db_session, base_dir=tmp_path)

    assert snapshot.status == SNAPSHOT_FAILED and "IS.AIR.GOOD.MT.K1" in snapshot.error
    assert (await db_session.execute(select(WorldBankIndicator))).scalars().all() == []


async def test_latest_computes_yoy_against_the_previous_year(db_session):
    db_session.add_all([
        WorldBankIndicator(indicator="IS.AIR.PSGR", year=2022, value=100.0),
        WorldBankIndicator(indicator="IS.AIR.PSGR", year=2023, value=110.0),
        WorldBankIndicator(indicator="NY.GDP.MKTP.KD.ZG", year=2020, value=-5.0),
        WorldBankIndicator(indicator="NY.GDP.MKTP.KD.ZG", year=2023, value=7.0),  # 2022 missing: no yoy
        WorldBankIndicator(indicator="IS.AIR.GOOD.MT.K1", year=2022, value=0.0),
        WorldBankIndicator(indicator="IS.AIR.GOOD.MT.K1", year=2023, value=5.0),  # previous is zero: no yoy
    ])
    await db_session.flush()

    latest = await world_bank_latest(db_session)

    assert latest["IS.AIR.PSGR"] == {"year": 2023, "value": 110.0, "yoy_pct": 10.0}
    assert latest["NY.GDP.MKTP.KD.ZG"] == {"year": 2023, "value": 7.0, "yoy_pct": None}
    assert latest["IS.AIR.GOOD.MT.K1"]["yoy_pct"] is None


async def test_latest_is_empty_without_rows(db_session):
    assert await world_bank_latest(db_session) == {}


def _client(db_session) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_api_returns_empty_list_without_data(db_session):
    async with _client(db_session) as client:
        response = await client.get("/api/datasets/world-bank")
    assert response.status_code == 200 and response.json() == []


async def test_api_returns_exactly_the_latest_value_of_each_indicator(db_session):
    db_session.add_all([
        WorldBankIndicator(indicator="IS.AIR.PSGR", year=2022, value=100.0),
        WorldBankIndicator(indicator="IS.AIR.PSGR", year=2023, value=110.0),
        WorldBankIndicator(indicator="NY.GDP.MKTP.KD.ZG", year=2025, value=7.5),
    ])
    await db_session.flush()

    async with _client(db_session) as client:
        body = (await client.get("/api/datasets/world-bank")).json()

    assert body == [
        {"indicator": "IS.AIR.PSGR", "label": "Air passengers carried", "unit": "passengers", "year": 2023,
         "value": 110.0, "yoy_pct": 10.0},
        {"indicator": "NY.GDP.MKTP.KD.ZG", "label": "GDP growth", "unit": "% per year", "year": 2025,
         "value": 7.5, "yoy_pct": None},
    ]

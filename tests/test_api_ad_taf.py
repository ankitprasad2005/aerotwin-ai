from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.datasets import router
from app.api.deps import get_db
from app.datasets import queries
from app.models.external import WeatherTaf
from tests.ad_taf_data import add_directives, add_tafs
from tests.weather_data import ICAO, OBSERVED_AT, add_weather


def _client(db_session) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_directives_endpoint_is_an_empty_list_without_data(db_session):
    async with _client(db_session) as client:
        response = await client.get("/api/datasets/airworthiness-directives")

    assert response.status_code == 200 and response.json() == []


async def test_directives_endpoint_returns_exactly_the_contract_newest_first_within_365_days(db_session):
    today = date.today()
    await add_directives(
        db_session,
        ("2026-00001", 100, ["A320"]),
        ("2026-00002", 10, ["A320", "A321"]),
        ("2026-00003", 10, ["B737"]),  # same day as the previous one: higher document number first
        ("2025-00009", 366, ["A320"]),  # outside the window
        ("2025-00008", 365, ["A321"]),  # exactly on the edge
    )

    async with _client(db_session) as client:
        body = (await client.get("/api/datasets/airworthiness-directives")).json()

    assert [ad["document_number"] for ad in body] == ["2026-00003", "2026-00002", "2026-00001", "2025-00008"]
    assert body[0] == {
        "document_number": "2026-00003",
        "title": "Airworthiness Directives; Airbus SAS Airplanes",
        "publication_date": (today - timedelta(days=10)).isoformat(),
        "html_url": "https://www.federalregister.gov/d/2026-00003",
        "aircraft_types": ["B737"],
    }
    assert all(set(ad) == {"document_number", "title", "publication_date", "html_url", "aircraft_types"} for ad in body)
    assert body[1]["aircraft_types"] == ["A320", "A321"]


async def test_query_filters_directives_by_aircraft_type(db_session):
    await add_directives(db_session, ("a", 5, ["A320"]), ("b", 4, ["A320", "A321"]), ("c", 3, ["B737"]))

    assert [d.document_number for d in await queries.airworthiness_directives(db_session, "A320")] == ["b", "a"]
    assert [d.document_number for d in await queries.airworthiness_directives(db_session, "A321")] == ["b"]
    assert [d.document_number for d in await queries.airworthiness_directives(db_session, "B737")] == ["c"]
    assert await queries.airworthiness_directives(db_session, "A380") == []


async def test_weather_entries_carry_the_taf_keys_additively(db_session):
    await add_weather(db_session, observations={"BOM": "IFR"}, forecasts={})
    await add_tafs(db_session, {"BOM": ("LIFR", True), "DEL": ("VFR", False)})

    async with _client(db_session) as client:
        body = {w["airport"]: w for w in (await client.get("/api/datasets/weather")).json()}

    assert body["BOM"]["taf_worst_flight_category_24h"] == "LIFR" and body["BOM"]["taf_thunderstorm_24h"] is True
    assert body["DEL"]["taf_worst_flight_category_24h"] == "VFR" and body["DEL"]["taf_thunderstorm_24h"] is False
    assert body["BLR"]["taf_worst_flight_category_24h"] is None and body["BLR"]["taf_thunderstorm_24h"] is None
    # The existing keys are untouched.
    assert {"airport", "icao", "observed_at", "flight_category", "wind_kt", "gust_kt", "visibility_sm", "ceiling_ft",
            "raw_text", "forecast"} <= set(body["BOM"])
    assert body["BOM"]["flight_category"] == "IFR" and body["BOM"]["icao"] == "VABB"


async def test_the_newest_taf_issue_of_an_airport_is_the_one_reported(db_session):
    await add_tafs(db_session, {"BOM": ("VFR", False)})
    db_session.add(WeatherTaf(
        airport="BOM", icao=ICAO["BOM"], issued_at=OBSERVED_AT + timedelta(hours=6), valid_from=OBSERVED_AT,
        valid_to=OBSERVED_AT + timedelta(hours=36), worst_flight_category_24h="IFR", thunderstorm_24h=True, raw_text="NEW",
    ))
    await db_session.flush()

    async with _client(db_session) as client:
        body = {w["airport"]: w for w in (await client.get("/api/datasets/weather")).json()}

    assert body["BOM"]["taf_worst_flight_category_24h"] == "IFR" and body["BOM"]["taf_thunderstorm_24h"] is True

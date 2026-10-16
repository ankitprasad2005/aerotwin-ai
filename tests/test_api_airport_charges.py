from datetime import date

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.datasets import router
from app.api.deps import get_db
from app.datasets import airport_charges
from app.models.external import FxRate


def _client(db_session) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_airport_charges_rows_are_empty_before_a_refresh(db_session):
    async with _client(db_session) as client:
        response = await client.get("/api/datasets/airport-charges")
    assert response.status_code == 200 and response.json() == []


async def test_airport_charges_lists_rows_with_their_sources(db_session):
    await airport_charges.fetch_airport_charges(db_session)
    async with _client(db_session) as client:
        everything = (await client.get("/api/datasets/airport-charges")).json()
        bom = (await client.get("/api/datasets/airport-charges", params={"airport": "bom"})).json()
        nowhere = (await client.get("/api/datasets/airport-charges", params={"airport": "ZZZ"})).json()

    assert len(everything) > len(bom) > 0 and nowhere == []
    landing = next(r for r in bom if r["charge_type"] == "landing")
    assert landing["airport"] == "BOM" and landing["rate_inr"] == 402.0 and landing["basis"] == "per_tonne"
    assert landing["currency"] == "INR" and landing["applies_to"] == "domestic"
    assert landing["effective_from"] == "2025-05-16" and landing["effective_to"] == "2029-03-31"
    assert landing["source_url"].endswith("17466350622028.pdf") and landing["page"] == "501"
    assert landing["source_title"].startswith("AERA Order No. 01/2025-26")
    assert {"slab_from_tonnes", "slab_to_tonnes", "base_inr"} <= set(landing)


async def test_turnaround_endpoint_returns_the_computed_breakdown(db_session):
    await airport_charges.fetch_airport_charges(db_session)
    db_session.add(FxRate(base="USD", quote="INR", rate_date=date(2026, 10, 16), rate=85.0))
    await db_session.flush()
    async with _client(db_session) as client:
        response = await client.get(
            "/api/datasets/airport-charges/turnaround",
            params={"airport": "BOM", "aircraft_type": "A320", "parking_hours": 4, "on_date": "2026-10-16"},
        )
    body = response.json()
    assert response.status_code == 200
    # landing 402 * 78 = 31,356; parking (4 - 2) h * 27 * 78 = 4,212
    assert (body["landing_inr"], body["parking_inr"], body["total_inr"]) == (31356.0, 4212.0, 35568.0)
    assert body["total_usd"] == 418.45 and body["mtow_tonnes"] == 78.0
    assert body["passenger_charges"]["embarking_inr"] == 175.0
    assert body["sources"]


async def test_turnaround_endpoint_defaults_and_stand_choice(db_session):
    await airport_charges.fetch_airport_charges(db_session)
    async with _client(db_session) as client:
        default = (await client.get("/api/datasets/airport-charges/turnaround", params={"airport": "DEL", "aircraft_type": "B737"})).json()
        remote = (
            await client.get(
                "/api/datasets/airport-charges/turnaround",
                params={"airport": "DEL", "aircraft_type": "A321", "parking_hours": 6, "stand": "remote", "on_date": "2026-10-16"},
            )
        ).json()
    assert default["parking_hours"] == 1.0 and default["total_usd"] is None  # no FX stored
    # A321 93.5 t -> next MT 94; landing 347 * 94 = 32,618; remote parking 5 h: 4 h * 18 * 94 + 1 h * 2 * 18 * 94 = 6,768 + 3,384
    assert (remote["landing_inr"], remote["parking_inr"]) == (32618.0, 10152.0)


async def test_turnaround_endpoint_errors(db_session):
    async with _client(db_session) as client:
        missing = await client.get("/api/datasets/airport-charges/turnaround", params={"airport": "BOM"})
        no_data = await client.get("/api/datasets/airport-charges/turnaround", params={"airport": "BOM", "aircraft_type": "A320"})
        await airport_charges.fetch_airport_charges(db_session)
        unknown = await client.get("/api/datasets/airport-charges/turnaround", params={"airport": "BOM", "aircraft_type": "A380"})
        negative = await client.get(
            "/api/datasets/airport-charges/turnaround", params={"airport": "BOM", "aircraft_type": "A320", "parking_hours": -1}
        )
        bad_stand = await client.get(
            "/api/datasets/airport-charges/turnaround", params={"airport": "BOM", "aircraft_type": "A320", "stand": "hangar"}
        )
    assert missing.status_code == 422
    assert no_data.status_code == 404 and "BOM" in no_data.json()["detail"]
    assert unknown.status_code == 404 and "A380" in unknown.json()["detail"]
    assert negative.status_code == 422 and bad_stand.status_code == 422

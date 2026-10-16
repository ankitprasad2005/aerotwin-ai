from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.datasets import router
from app.api.deps import get_db
from app.models.external import AirportTrafficMonthly, IndiaAirport, IndiaRunway


def _client(db_session) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _airport(ident, name, city, iata=None, type_="large_airport", scheduled=True, elevation=39.0):
    return IndiaAirport(
        ident=ident, icao_code=ident if len(ident) == 4 else None, iata_code=iata, name=name, airport_type=type_,
        municipality=city, latitude_deg=19.0, longitude_deg=72.8, elevation_ft=elevation, scheduled_service=scheduled,
        frequency_count=7,
    )


def _runway(oid, ident, length, le="09", he="27", closed=False):
    return IndiaRunway(
        ourairports_id=oid, airport_ident=ident, length_ft=length, width_ft=150.0, surface="ASP", lighted=True,
        closed=closed, le_ident=le, he_ident=he,
    )


async def _seed_airports(db):
    db.add_all(
        [
            _airport("VABB", "Chhatrapati Shivaji Maharaj International Airport", "Mumbai", "BOM"),
            _airport("VIDP", "Indira Gandhi International Airport", "New Delhi", "DEL", elevation=777.0),
            _airport("VAJJ", "Juhu Airport", "Mumbai", None, "small_airport", False),
            _airport("IN-0001", "Mumbai 100%_Helipad", "Mumbai", None, "heliport", False, elevation=None),
            _runway(1, "VABB", 11511.0),
            _runway(2, "VABB", 9419.0, "14", "32"),
            _runway(3, "VABB", 12000.0, "05", "23", closed=True),
            _runway(4, "VIDP", 14534.0, "11", "29"),
        ]
    )
    await db.flush()


async def test_india_airports_empty(db_session):
    async with _client(db_session) as client:
        response = await client.get("/api/datasets/india-airports")

    assert response.status_code == 200
    assert response.json() == {"total": 0, "limit": 50, "offset": 0, "items": []}


async def test_india_airports_lists_big_scheduled_airports_first_with_a_runway_summary(db_session):
    await _seed_airports(db_session)
    async with _client(db_session) as client:
        body = (await client.get("/api/datasets/india-airports")).json()

    assert body["total"] == 4
    assert [a["ident"] for a in body["items"]] == ["VABB", "VIDP", "VAJJ", "IN-0001"]
    mumbai = body["items"][0]
    assert mumbai["iata"] == "BOM" and mumbai["icao"] == "VABB" and mumbai["city"] == "Mumbai"
    assert mumbai["scheduled_service"] is True and mumbai["frequency_count"] == 7 and mumbai["elevation_ft"] == 39.0
    assert mumbai["runway_count"] == 3
    assert mumbai["longest_runway_ft"] == 11511.0  # the closed 12000 ft runway does not count
    assert mumbai["runways"][0] == {
        "designator": "05/23", "length_ft": 12000.0, "width_ft": 150.0, "surface": "ASP", "lighted": True, "closed": True,
    }
    assert body["items"][3]["runway_count"] == 0 and body["items"][3]["longest_runway_ft"] is None


async def test_india_airports_search_matches_code_name_and_city(db_session):
    await _seed_airports(db_session)
    async with _client(db_session) as client:
        by_iata = (await client.get("/api/datasets/india-airports", params={"q": "del"})).json()
        by_icao = (await client.get("/api/datasets/india-airports", params={"q": "vabb"})).json()
        by_name = (await client.get("/api/datasets/india-airports", params={"q": "indira gandhi"})).json()
        by_city = (await client.get("/api/datasets/india-airports", params={"q": "MUMBAI"})).json()
        wildcard = (await client.get("/api/datasets/india-airports", params={"q": "100%_"})).json()
        none = (await client.get("/api/datasets/india-airports", params={"q": "zzz"})).json()

    assert [a["ident"] for a in by_iata["items"]] == ["VIDP"]
    assert [a["ident"] for a in by_icao["items"]] == ["VABB"]
    assert [a["ident"] for a in by_name["items"]] == ["VIDP"]
    assert [a["ident"] for a in by_city["items"]] == ["VABB", "VAJJ", "IN-0001"]
    assert [a["ident"] for a in wildcard["items"]] == ["IN-0001"]  # % and _ are literal
    assert none["total"] == 0 and none["items"] == []


async def test_india_airports_paging(db_session):
    await _seed_airports(db_session)
    async with _client(db_session) as client:
        page = (await client.get("/api/datasets/india-airports", params={"limit": 2, "offset": 1})).json()
        bad_limit = await client.get("/api/datasets/india-airports", params={"limit": 0})
        too_big = await client.get("/api/datasets/india-airports", params={"limit": 501})
        bad_offset = await client.get("/api/datasets/india-airports", params={"offset": -1})

    assert page["total"] == 4 and page["limit"] == 2 and page["offset"] == 1
    assert [a["ident"] for a in page["items"]] == ["VIDP", "VAJJ"]
    assert bad_limit.status_code == too_big.status_code == bad_offset.status_code == 422


def _traffic(name, iata, period, passengers, movements=100, **extra):
    return AirportTrafficMonthly(
        airport_name=name, iata_code=iata, icao_code=None, period=period, aircraft_movements=movements,
        passengers=passengers, freight_tonnes=12.5, **extra,
    )


async def _seed_traffic(db):
    db.add_all(
        [
            _traffic("MUMBAI (MIAL)", "BOM", "2026-08", 4050443, 26017, passengers_yoy_pct=-10.4, movements_domestic=18644),
            _traffic("MUMBAI (MIAL)", "BOM", "2026-07", 4200000),
            _traffic("DELHI", "DEL", "2026-08", 6083616),
            _traffic("JUHU", None, "2026-08", None),
        ]
    )
    await db.flush()


async def test_airport_traffic_empty(db_session):
    async with _client(db_session) as client:
        response = await client.get("/api/datasets/airport-traffic")

    assert response.json() == {"total": 0, "limit": 50, "offset": 0, "items": []}


async def test_airport_traffic_newest_month_and_busiest_airport_first(db_session):
    await _seed_traffic(db_session)
    async with _client(db_session) as client:
        body = (await client.get("/api/datasets/airport-traffic")).json()

    assert body["total"] == 4
    assert [(t["airport_name"], t["period"]) for t in body["items"]] == [
        ("DELHI", "2026-08"), ("MUMBAI (MIAL)", "2026-08"), ("JUHU", "2026-08"), ("MUMBAI (MIAL)", "2026-07"),
    ]
    mumbai = body["items"][1]
    assert mumbai["iata"] == "BOM" and mumbai["passengers"] == 4050443 and mumbai["aircraft_movements"] == 26017
    assert mumbai["freight_tonnes"] == 12.5 and mumbai["passengers_yoy_pct"] == -10.4 and mumbai["movements_domestic"] == 18644
    assert mumbai["movements_international"] is None and mumbai["freight_yoy_pct"] is None


async def test_airport_traffic_filters_by_code_or_name_and_pages(db_session):
    await _seed_traffic(db_session)
    async with _client(db_session) as client:
        bom = (await client.get("/api/datasets/airport-traffic", params={"airport": "bom"})).json()
        by_name = (await client.get("/api/datasets/airport-traffic", params={"airport": "delh"})).json()
        page = (await client.get("/api/datasets/airport-traffic", params={"airport": "BOM", "limit": 1, "offset": 1})).json()
        invalid = await client.get("/api/datasets/airport-traffic", params={"limit": 1000})

    assert [t["period"] for t in bom["items"]] == ["2026-08", "2026-07"] and bom["total"] == 2
    assert [t["iata"] for t in by_name["items"]] == ["DEL"]
    assert page["total"] == 2 and [t["period"] for t in page["items"]] == ["2026-07"]
    assert invalid.status_code == 422

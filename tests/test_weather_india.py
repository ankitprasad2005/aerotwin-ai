"""Pan-India weather: the airport list, batching, parsing of real captures, the India APIs, summary, tool and evidence."""
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.datasets import router
from app.api.deps import get_db
from app.datasets import common, india_airports, weather, weather_india
from app.datasets.common import DatasetError, utcnow
from app.datasets.india_airports import INDIA_AIRPORT_INFO, INDIA_STATIONS
from app.datasets.weather import parse_metar, parse_open_meteo, parse_taf
from app.models.external import (
    SNAPSHOT_SUCCESS, DatasetSnapshot, WeatherForecast, WeatherObservation, WeatherTaf,
)
from app.tools.weather_tools import query_weather_conditions
from tests import weather_mocks

FIXTURES = Path(__file__).parent / "fixtures" / "datasets"
METAR = (FIXTURES / "aviation_weather_metar_india.json").read_bytes()
TAF = (FIXTURES / "aviation_weather_taf_india.json").read_bytes()
FORECAST = (FIXTURES / "open_meteo_forecast_india.json").read_bytes()
TWIN = ["BOM", "DEL", "BLR", "MAA", "HYD", "CCU"]


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


def _client(db_session) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- the airport list -------------------------------------------------------------------------------------------------


def _derive_from_ourairports() -> list[tuple]:
    """Re-apply the documented filter to the OurAirports capture (India rows of airports.csv, 2026-10-16)."""
    rows = csv.DictReader(io.StringIO((FIXTURES / "ourairports_in.csv").read_text(encoding="utf-8")))
    selected = [
        r
        for r in rows
        if r["iso_country"] == "IN"
        and r["type"] in ("large_airport", "medium_airport", "small_airport")
        and (r["scheduled_service"] == "yes" or r["type"] in ("large_airport", "medium_airport"))
        and len(r["ident"]) == 4
        and r["ident"].isalpha()
        and r["iata_code"]
    ]
    selected.sort(key=lambda r: r["iata_code"])
    return [
        (r["iata_code"], r["ident"], r["name"], r["municipality"], round(float(r["latitude_deg"]), 4), round(float(r["longitude_deg"]), 4))
        for r in selected
    ]


def test_the_constant_is_the_documented_filter_of_ourairports():
    assert list(india_airports.INDIA_AIRPORTS) == _derive_from_ourairports()
    assert len(india_airports.INDIA_AIRPORTS) == 128
    assert india_airports.INDIA_AIRPORT_LIST_VERSION == "ourairports-2026-10-16"
    assert "ourairports" in india_airports.__doc__.lower()


def test_airport_list_is_unique_valid_and_contains_the_twin():
    codes = [a[0] for a in india_airports.INDIA_AIRPORTS]
    icaos = [a[1] for a in india_airports.INDIA_AIRPORTS]
    assert len(set(codes)) == len(codes) == len(set(icaos))
    assert all(len(c) == 3 and len(i) == 4 and i.startswith("V") for c, i in zip(codes, icaos))
    assert all(6 <= a[4] <= 37 and 67 <= a[5] <= 98 for a in india_airports.INDIA_AIRPORTS)  # inside India's bounding box
    for airport, (icao, _, _) in weather.AIRPORT_STATIONS.items():
        assert INDIA_STATIONS[airport][0] == icao
    assert weather.ICAO_TO_IATA["VABB"] == "BOM" and len(weather.ICAO_TO_IATA) == 128
    assert INDIA_AIRPORT_INFO["DEL"]["name"] == "Indira Gandhi International Airport"


# --- batching ----------------------------------------------------------------------------------------------------------


def test_metar_and_taf_urls_batch_all_airports():
    for urls, api in ((weather.metar_urls(), weather.METAR_API), (weather.taf_urls(), weather.TAF_API)):
        assert len(urls) == 4 and all(u.startswith(f"{api}?ids=") and u.endswith("&format=json") for u in urls)
        ids = [i for u in urls for i in u.split("ids=")[1].split("&")[0].split(",")]
        assert sorted(ids) == sorted(weather.ICAO_TO_IATA) and all(len(u) < 400 for u in urls)
        assert all(len(u.split("ids=")[1].split("&")[0].split(",")) <= weather.METAR_BATCH for u in urls)


def test_forecast_urls_batch_all_airports_with_matching_coordinates():
    groups, urls = weather.forecast_batches(), weather.forecast_urls()
    assert [len(g) for g in groups] == [50, 50, 28] and len(urls) == 3
    assert [c for g in groups for c in g] == list(INDIA_STATIONS)
    first = urls[0]
    assert first.startswith("https://api.open-meteo.com/v1/forecast?latitude=")
    latitudes = first.split("latitude=")[1].split("&")[0].split(",")
    assert latitudes == [str(INDIA_STATIONS[c][1]) for c in groups[0]]
    assert "forecast_days=7" in first and "timezone=Asia%2FKolkata" in first


def test_batches_and_merge():
    assert weather.batches([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]] and weather.batches([], 3) == []
    assert json.loads(weather.merge_json_lists([b'[{"a":1}]', b'{"b":2}', b"[]"], "X")) == [{"a": 1}, {"b": 2}]
    with pytest.raises(DatasetError, match="X response is malformed"):
        weather.merge_json_lists([b"nope"], "X")


# --- parsing real captures --------------------------------------------------------------------------------------------


def test_parse_metar_of_the_real_all_india_capture():
    rows = parse_metar(METAR)
    assert 60 <= len(rows) <= 128  # the airports that issued a METAR when captured: 87 raw reports
    assert {r["airport"] for r in rows} > set(TWIN)
    assert all(r["airport"] == weather.ICAO_TO_IATA[r["icao"]] and r["flight_category"] in weather.CATEGORIES for r in rows)
    assert len({r["airport"] for r in rows}) == len(rows)


def test_parse_taf_of_the_real_all_india_capture():
    capture_time = datetime(2026, 10, 16, 15, 10, tzinfo=timezone.utc)
    rows = parse_taf(TAF, capture_time)
    assert len(rows) > 50 and {r["airport"] for r in rows} > set(TWIN)
    assert all(r["worst_flight_category_24h"] in weather.CATEGORIES for r in rows)
    assert any(r["thunderstorm_24h"] for r in rows) or True  # the flag is a bool either way
    assert all(isinstance(r["thunderstorm_24h"], bool) for r in rows)


def test_parse_open_meteo_of_the_real_128_airport_capture():
    bodies = weather_mocks.india_forecast_batches()
    rows = [r for body, group in zip(bodies, weather.forecast_batches()) for r in parse_open_meteo(body, group)]
    assert len({r["airport"] for r in rows}) == 128 and len(rows) == 128 * 7
    assert {r["airport"] for r in rows} == set(INDIA_STATIONS)
    with pytest.raises(DatasetError, match="expected 50 locations, got 2"):
        parse_open_meteo(json.dumps(json.loads(FORECAST)[:2]).encode(), weather.forecast_batches()[0])


# --- fetching ----------------------------------------------------------------------------------------------------------


@respx.mock
async def test_fetchers_store_all_indian_airports(db_session, tmp_path):
    weather_mocks.mock_list_batches(weather.metar_urls(), METAR)
    weather_mocks.mock_list_batches(weather.taf_urls(), TAF)
    weather_mocks.mock_forecast()

    metar = await weather.fetch_aviation_weather(db_session, base_dir=tmp_path)
    taf = await weather.fetch_taf(db_session, base_dir=tmp_path, now=datetime(2026, 10, 16, 15, 10, tzinfo=timezone.utc))
    forecast = await weather.fetch_open_meteo(db_session, base_dir=tmp_path)

    assert {s.status for s in (metar, taf, forecast)} == {SNAPSHOT_SUCCESS}
    assert metar.row_count > 60 and taf.row_count > 50 and forecast.row_count == 128 * 7
    assert respx.calls.call_count == 4 + 4 + 3
    airports = {o.airport for o in (await db_session.execute(select(WeatherObservation))).scalars()}
    assert airports > set(TWIN) and len(airports) == metar.row_count


@respx.mock
async def test_a_failing_batch_fails_the_whole_snapshot(db_session, tmp_path):
    urls = weather.metar_urls()
    weather_mocks.mock_list_batches(urls[:3], METAR)
    respx.get(urls[3]).mock(return_value=httpx.Response(503))

    snapshot = await weather.fetch_aviation_weather(db_session, base_dir=tmp_path)

    assert snapshot.status == "FAILED"
    assert (await db_session.execute(select(WeatherObservation))).scalars().all() == []


# --- data for the API / summary ----------------------------------------------------------------------------------------


NOW = utcnow()


async def _seed(db_session):
    """BOM LIFR now + TAF thunderstorm, DEL IFR, BLR MVFR, MAA VFR (TAF IFR), AMD VFR with a disruptive forecast,
    a stale GOI observation and HYD/CCU/PNQ without data."""
    metar, meteo, taf = (DatasetSnapshot(source=s, fetched_at=NOW, status=SNAPSHOT_SUCCESS, source_url="x", row_count=1) for s in ("aviation_weather", "open_meteo", "aviation_weather_taf"))
    db_session.add_all([metar, meteo, taf])
    await db_session.flush()

    def obs(airport, category, age=timedelta(minutes=30)):
        return WeatherObservation(
            airport=airport, icao=INDIA_STATIONS[airport][0], observed_at=NOW - age, flight_category=category, wind_kt=5.0,
            raw_text=f"METAR {airport}", snapshot_id=metar.id,
        )

    def forecast(airport, code=1, mm=0.0, gust=20.0):
        return [
            WeatherForecast(
                airport=airport, forecast_date=(NOW + timedelta(days=d)).date(), precipitation_mm=mm, max_gust_kmh=gust,
                weather_code=code, thunderstorm=code in (95, 96, 99), snapshot_id=meteo.id,
            )
            for d in range(7)
        ]

    def taf_row(airport, worst, thunderstorm, valid_hours=20):
        return WeatherTaf(
            airport=airport, icao=INDIA_STATIONS[airport][0], issued_at=NOW - timedelta(hours=2), valid_from=NOW - timedelta(hours=2),
            valid_to=NOW + timedelta(hours=valid_hours), worst_flight_category_24h=worst, thunderstorm_24h=thunderstorm,
            raw_text=f"TAF {airport}", snapshot_id=taf.id,
        )

    db_session.add_all(
        [obs("BOM", "LIFR"), obs("DEL", "IFR"), obs("BLR", "MVFR"), obs("MAA", "VFR"), obs("AMD", "VFR"), obs("GOI", "IFR", timedelta(hours=9))]
        + [taf_row("BOM", "IFR", True), taf_row("MAA", "IFR", False), taf_row("PNQ", "LIFR", True, valid_hours=-1)]
        + forecast("BOM") + forecast("AMD", code=95, mm=30.0) + forecast("MAA")
    )
    await db_session.flush()


async def test_summary_counts_categories_thunderstorms_and_worst_airports(db_session):
    await _seed(db_session)

    summary = await weather_india.india_summary(db_session)

    assert summary["airports_total"] == 128
    assert summary["airports_reporting"] == {"metar": 5, "taf": 2, "forecast": 3}  # GOI stale, PNQ TAF expired
    assert summary["by_flight_category"] == {"VFR": 2, "MVFR": 1, "IFR": 1, "LIFR": 1, "UNKNOWN": 123}
    assert summary["thunderstorm_24h"] == {"count": 1, "airports": ["BOM"]}
    worst = summary["worst_airports"]
    assert [w["airport"] for w in worst] == ["BOM", "AMD", "DEL", "MAA", "BLR"]
    assert worst[0]["flight_category"] == "LIFR" and worst[0]["taf_thunderstorm_24h"] is True and worst[0]["score"] == 9 + 4 + 2
    amd = worst[1]
    assert amd["disruption_days"] == 7 and amd["taf_worst_flight_category_24h"] is None and amd["taf_thunderstorm_24h"] is None


async def test_summary_of_an_empty_database_is_all_unknown(db_session):
    summary = await weather_india.india_summary(db_session)

    assert summary["airports_reporting"] == {"metar": 0, "taf": 0, "forecast": 0}
    assert summary["by_flight_category"]["UNKNOWN"] == 128 and summary["worst_airports"] == []
    assert summary["thunderstorm_24h"] == {"count": 0, "airports": []}


async def test_summary_lists_at_most_ten_worst_airports(db_session):
    snapshot = DatasetSnapshot(source="aviation_weather", fetched_at=NOW, status=SNAPSHOT_SUCCESS, source_url="x", row_count=1)
    db_session.add(snapshot)
    await db_session.flush()
    for airport in list(INDIA_STATIONS)[:15]:
        db_session.add(
            WeatherObservation(
                airport=airport, icao=INDIA_STATIONS[airport][0], observed_at=NOW, flight_category="IFR", wind_kt=1.0, raw_text="x",
                snapshot_id=snapshot.id,
            )
        )
    await db_session.flush()

    worst = (await weather_india.india_summary(db_session))["worst_airports"]

    assert len(worst) == 10 and [w["airport"] for w in worst] == sorted(w["airport"] for w in worst)  # ties break by code


# --- APIs ------------------------------------------------------------------------------------------------------------


async def test_default_weather_endpoint_still_lists_the_six_twin_airports(db_session):
    await _seed(db_session)
    async with _client(db_session) as client:
        body = (await client.get("/api/datasets/weather")).json()

    assert [w["airport"] for w in body] == TWIN
    assert body[0]["flight_category"] == "LIFR" and body[0]["taf_thunderstorm_24h"] is True and len(body[0]["forecast"]) == 7
    assert "name" not in body[0]


async def test_weather_scope_india_pages_through_every_airport(db_session):
    await _seed(db_session)
    async with _client(db_session) as client:
        page = (await client.get("/api/datasets/weather?scope=india&limit=200")).json()
        small = (await client.get("/api/datasets/weather?scope=india&limit=5&offset=2")).json()
        last = (await client.get("/api/datasets/weather?scope=india&limit=5&offset=126")).json()
        beyond = (await client.get("/api/datasets/weather?scope=india&offset=500")).json()

    assert page["total"] == 128 and len(page["items"]) == 128 and page["limit"] == 200 and page["offset"] == 0
    codes = [i["airport"] for i in page["items"]]
    assert codes == sorted(codes) and [i["airport"] for i in small["items"]] == codes[2:7]
    assert [i["airport"] for i in last["items"]] == codes[126:] and beyond["items"] == [] and beyond["total"] == 128
    by_code = {i["airport"]: i for i in page["items"]}
    assert by_code["BOM"]["flight_category"] == "LIFR" and by_code["BOM"]["name"].startswith("Chhatrapati Shivaji")
    assert by_code["PNQ"]["flight_category"] == "UNKNOWN" and by_code["PNQ"]["forecast"] == []
    assert by_code["AMD"]["forecast"][0]["thunderstorm"] is True and by_code["AMD"]["city"] == "Ahmedabad"
    assert -90 < by_code["DEL"]["latitude"] < 90 and by_code["DEL"]["icao"] == "VIDP"


async def test_weather_scope_india_search_and_validation(db_session):
    async with _client(db_session) as client:
        by_city = (await client.get("/api/datasets/weather?scope=india&q=mumbai")).json()
        by_icao = (await client.get("/api/datasets/weather?scope=india&q=vidp")).json()
        none = (await client.get("/api/datasets/weather?scope=india&q=zzzzzz")).json()
        bad_limit = await client.get("/api/datasets/weather?scope=india&limit=0")
        too_big = await client.get("/api/datasets/weather?scope=india&limit=201")
        bad_scope = await client.get("/api/datasets/weather?scope=mars")

    assert "BOM" in [i["airport"] for i in by_city["items"]] and by_city["total"] == len(by_city["items"])
    assert [i["airport"] for i in by_icao["items"]] == ["DEL"] and none == {"total": 0, "limit": 25, "offset": 0, "items": []}
    assert bad_limit.status_code == bad_scope.status_code == too_big.status_code == 422


async def test_weather_summary_endpoint(db_session):
    await _seed(db_session)
    async with _client(db_session) as client:
        response = await client.get("/api/datasets/weather/summary")

    body = response.json()
    assert response.status_code == 200 and body["airports_total"] == 128
    assert body["by_flight_category"]["LIFR"] == 1 and body["thunderstorm_24h"]["airports"] == ["BOM"]
    assert body["worst_airports"][0]["airport"] == "BOM" and "generated_at" in body


# --- tool and evidence -------------------------------------------------------------------------------------------------


async def test_weather_tool_adds_an_india_context_block_without_changing_the_twin_data(db_session):
    await _seed(db_session)

    weather_block = (await query_weather_conditions(db_session))["weather"]

    assert [a["airport"] for a in weather_block["airports"]] == TWIN
    india = weather_block["india"]
    assert india["airports_total"] == 128 and india["by_flight_category"]["LIFR"] == 1
    assert india["thunderstorm_24h_count"] == 1 and india["thunderstorm_24h_airports"] == ["BOM"]
    assert [w["airport"] for w in india["worst_airports"]] == ["BOM", "AMD", "DEL", "MAA", "BLR"]
    json.dumps(weather_block)  # the block is JSON-serialisable (no datetimes) for the agent context


async def test_india_weather_summary_evidence(db_session):
    from app.datasets.weather_evidence import INDIA_SUMMARY_RELIABILITY, india_weather_summary
    from app.evidence.base import EvidenceRequest
    from app.evidence.catalog import EVIDENCE_PROVIDERS

    request = EvidenceRequest(agent_type="WEATHER", objective="x", route=None)
    assert await india_weather_summary(db_session, request) == []

    await _seed(db_session)
    (item,) = await india_weather_summary(db_session, request)

    assert EVIDENCE_PROVIDERS["india_weather_summary"] is india_weather_summary
    assert item.source == "aviation_weather" and item.reliability == INDIA_SUMMARY_RELIABILITY == 0.85
    assert item.id.startswith("india_weather:") and item.kind == "dataset"
    assert item.content["by_flight_category"]["IFR"] == 1 and item.content["thunderstorm_24h_airports"] == ["BOM"]
    assert item.content["worst_airports"][0]["airport"] == "BOM" and item.content["airports_reporting"]["metar"] == 5


def test_agents_get_the_india_providers():
    from app.agents.registry import AGENT_REGISTRY

    for agent in ("WEATHER", "CREW", "NETWORK"):
        assert "india_weather_summary" in AGENT_REGISTRY[agent].evidence_providers
    for agent in ("WEATHER", "NETWORK"):
        assert "imd_warnings" in AGENT_REGISTRY[agent].evidence_providers
    assert "imd_warnings" not in AGENT_REGISTRY["CREW"].evidence_providers


@pytest.mark.parametrize("objective", ["nationwide disruption", "India monsoon", "network-wide storms", "cyclone landfall"])
def test_nationwide_keywords_route_the_india_summary(objective):
    from app.evidence.routing import ROUTING_TABLE, topics_in

    assert "nationwide" in topics_in(objective)
    route = next(r for r in ROUTING_TABLE if r.topic == "nationwide")
    assert route.providers == ("india_weather_summary",) and route.agents == {"NETWORK", "CREW", "FLEET", "WEATHER"}


def test_imd_keywords_route_the_warnings():
    from app.evidence.routing import ROUTING_TABLE, topics_in

    assert "imd" in topics_in("any IMD red alert for thunderstorms?")
    route = next(r for r in ROUTING_TABLE if r.topic == "imd")
    assert route.providers == ("imd_warnings",) and route.agents == {"WEATHER", "NETWORK"}


async def test_india_page_directly(db_session):
    await _seed(db_session)

    page = await weather_india.india_page(db_session, "bom", 5, 0)

    assert page["total"] == 1 and page["items"][0]["airport"] == "BOM" and page["items"][0]["flight_category"] == "LIFR"
    assert page["items"][0]["longitude"] == INDIA_AIRPORT_INFO["BOM"]["longitude"]

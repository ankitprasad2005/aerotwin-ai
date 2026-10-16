import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.datasets import router
from app.api.deps import get_db
from app.config import Settings
from app.datasets import common, opensky_live
from app.datasets.common import DatasetError
from app.datasets.opensky_live import fetch_opensky_live, parse_states, previous_utc_day
from app.datasets.traffic_evidence import live_air_traffic
from app.evidence.base import EvidenceRequest
from app.models.external import (
    SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, AirportTrafficLive, AirTrafficSnapshot, DatasetSnapshot,
)

FIXTURE = (Path(__file__).parent / "fixtures" / "datasets" / "opensky_states_india.json").read_bytes()
TAKEN_AT = datetime.fromtimestamp(json.loads(FIXTURE)["time"], tz=timezone.utc)
STATES = opensky_live.states_url()
FLIGHTS = opensky_live.API_ROOT + "/flights/"


@pytest.fixture(autouse=True)
def tmp_datasets(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "get_settings", lambda: type("S", (), {"datasets_dir": str(tmp_path)})())
    return tmp_path


def _credentials(monkeypatch, client_id="id", secret="secret"):
    settings = Settings(_env_file=None, opensky_client_id=client_id, opensky_client_secret=secret)
    monkeypatch.setattr(opensky_live, "get_settings", lambda: settings)


@pytest.fixture(autouse=True)
def anonymous(monkeypatch):
    monkeypatch.setattr(opensky_live, "get_settings", lambda: Settings(_env_file=None))


def test_parse_states_skips_vectors_without_position():
    body = json.dumps({"time": 1792163906, "states": [
        ["a", "IGO1 ", "India", 1, 1, 77.1, 28.5, 100.0, False, 200.0, 10, 0, None, 120, None, False, 0],
        ["b", None, "India", 1, 1, None, None, None, True, None, None, None, None, None, None, False, 0],
        ["c"],  # truncated record
    ]}).encode()
    taken_at, vectors = parse_states(body)
    assert taken_at == datetime.fromtimestamp(1792163906, tz=timezone.utc)
    assert [(v.icao24, v.callsign, v.on_ground, v.velocity_ms) for v in vectors] == [("a", "IGO1", False, 200.0)]


@pytest.mark.parametrize("body", [b"not json", b'{"time": 1}', b'{"time": 1, "states": null}', b"[]"])
def test_parse_states_rejects_malformed(body):
    with pytest.raises(DatasetError, match="malformed"):
        parse_states(body)


def test_previous_utc_day():
    now = datetime(2026, 10, 16, 15, 30, tzinfo=timezone.utc)
    begin, end = previous_utc_day(now)
    assert begin == int(datetime(2026, 10, 15, tzinfo=timezone.utc).timestamp())
    assert end == int(datetime(2026, 10, 16, tzinfo=timezone.utc).timestamp()) - 1


def test_states_url_covers_the_india_box():
    assert STATES == "https://opensky-network.org/api/states/all?lamin=6&lomin=68&lamax=36&lomax=98"


@respx.mock
async def test_anonymous_fetch_stores_totals_and_airport_rows(db_session):
    route = respx.get(STATES).mock(
        return_value=httpx.Response(200, content=FIXTURE, headers={"X-Rate-Limit-Remaining": "370"})
    )
    flights = respx.get(url__startswith=FLIGHTS)
    token = respx.post(opensky_live.TOKEN_URL)

    snapshot = await fetch_opensky_live(db_session)

    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.row_count == 32
    assert route.calls[0].request.headers.get("authorization") is None
    assert not flights.called and not token.called  # anonymous: no auth, no flights endpoints
    assert snapshot.details["authenticated"] is False and snapshot.details["credits_remaining"] == "370"
    total = (await db_session.execute(select(AirTrafficSnapshot))).scalar_one()
    assert total.taken_at == TAKEN_AT and total.snapshot_id == snapshot.id
    assert total.airborne + total.on_ground == total.aircraft_over_india > 100
    rows = {r.airport: r for r in (await db_session.execute(select(AirportTrafficLive))).scalars().all()}
    assert len(rows) == 32 and rows["DEL"].icao == "VIDP" and rows["DEL"].aircraft_within_radius >= 10
    assert rows["DEL"].on_ground_nearby + rows["DEL"].airborne_nearby == rows["DEL"].aircraft_within_radius
    assert all(r.arrivals_last_24h is None and r.departures_last_24h is None for r in rows.values())


@respx.mock
async def test_refetch_of_the_same_snapshot_time_upserts(db_session):
    respx.get(STATES).mock(return_value=httpx.Response(200, content=FIXTURE))
    await fetch_opensky_live(db_session)
    await fetch_opensky_live(db_session)
    assert len((await db_session.execute(select(AirTrafficSnapshot))).scalars().all()) == 1
    assert len((await db_session.execute(select(AirportTrafficLive))).scalars().all()) == 32


@respx.mock
async def test_rate_limit_is_a_failed_snapshot(db_session):
    route = respx.get(STATES).mock(
        return_value=httpx.Response(429, headers={"X-Rate-Limit-Retry-After-Seconds": "3600"})
    )

    snapshot = await fetch_opensky_live(db_session)

    assert snapshot.status == SNAPSHOT_FAILED and "rate limit" in snapshot.error and "3600" in snapshot.error
    assert route.call_count == 1  # never hammer a credit-limited API
    assert (await db_session.execute(select(AirTrafficSnapshot))).scalars().all() == []


@respx.mock
async def test_rate_limit_without_retry_header(db_session):
    respx.get(STATES).mock(return_value=httpx.Response(429))
    snapshot = await fetch_opensky_live(db_session)
    assert snapshot.status == SNAPSHOT_FAILED and "unknown number" in snapshot.error


@respx.mock
@pytest.mark.parametrize(
    "response,message",
    [
        (httpx.Response(500), "HTTP 500"),
        (httpx.Response(200, content=b'{"time": 1792163906, "states": []}'), "no state vectors"),
        (httpx.Response(200, content=b'{"time": 1792163906, "states": null}'), "malformed"),
        (httpx.ConnectError("boom"), "failed"),
    ],
)
async def test_bad_responses_are_failed_snapshots(db_session, response, message):
    respx.get(STATES).mock(side_effect=[response])
    snapshot = await fetch_opensky_live(db_session)
    assert snapshot.status == SNAPSHOT_FAILED and message in snapshot.error
    assert (await db_session.execute(select(AirportTrafficLive))).scalars().all() == []


def _mock_authenticated(count_arrivals=5, count_departures=7):
    respx.post(opensky_live.TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok"}))
    states = respx.get(STATES).mock(return_value=httpx.Response(200, content=FIXTURE))
    arrivals = respx.get(url__startswith=FLIGHTS + "arrival").mock(
        return_value=httpx.Response(200, json=[{"icao24": "x"}] * count_arrivals)
    )
    departures = respx.get(url__startswith=FLIGHTS + "departure").mock(
        return_value=httpx.Response(200, json=[{"icao24": "x"}] * count_departures)
    )
    return states, arrivals, departures


@respx.mock
async def test_authenticated_fetch_counts_previous_day_flights_for_the_twin_airports(db_session, monkeypatch):
    _credentials(monkeypatch)
    states, arrivals, departures = _mock_authenticated()

    snapshot = await fetch_opensky_live(db_session)

    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.details["authenticated"] is True
    assert states.calls[0].request.headers["authorization"] == "Bearer tok"
    assert arrivals.call_count == departures.call_count == 6
    assert b"client_id=id" in respx.calls[0].request.content
    rows = {r.airport: r for r in (await db_session.execute(select(AirportTrafficLive))).scalars().all()}
    assert (rows["DEL"].arrivals_last_24h, rows["DEL"].departures_last_24h) == (5, 7)
    assert rows["JAI"].arrivals_last_24h is None  # only the twin's six airports are queried
    query = dict(arrivals.calls[0].request.url.params)
    assert query["airport"] == "VABB" and int(query["end"]) - int(query["begin"]) == 86399


@respx.mock
async def test_flight_counts_are_fetched_once_per_utc_day(db_session, monkeypatch):
    _credentials(monkeypatch)
    now = datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(opensky_live, "utcnow", lambda: now)
    states, arrivals, departures = _mock_authenticated()
    await fetch_opensky_live(db_session)
    assert arrivals.call_count == 6

    # A later snapshot on the same UTC day reuses the stored counts.
    later = json.loads(FIXTURE)
    later["time"] = int(now.timestamp()) + 600
    states.mock(return_value=httpx.Response(200, content=json.dumps(later).encode()))
    monkeypatch.setattr(opensky_live, "utcnow", lambda: datetime(2026, 10, 16, 11, 0, tzinfo=timezone.utc))
    # taken_at (fixture time) is before 'today' in this synthetic clock, so seed today's row as an earlier snapshot.
    db_session.add(AirTrafficSnapshot(taken_at=now, aircraft_over_india=1, airborne=1, on_ground=0))
    for r in (await db_session.execute(select(AirportTrafficLive))).scalars().all():
        db_session.add(AirportTrafficLive(
            taken_at=now, airport=r.airport, icao=r.icao, aircraft_within_radius=0, on_ground_nearby=0,
            airborne_nearby=0, arrivals_last_24h=r.arrivals_last_24h, departures_last_24h=r.departures_last_24h,
        ))
    await db_session.flush()

    await fetch_opensky_live(db_session)

    assert arrivals.call_count == 6 and departures.call_count == 6  # no new flight calls
    newest = (await db_session.execute(
        select(AirportTrafficLive).where(AirportTrafficLive.airport == "DEL").order_by(AirportTrafficLive.taken_at.desc())
    )).scalars().first()
    assert newest.arrivals_last_24h == 5 and newest.departures_last_24h == 7


@respx.mock
async def test_refused_flight_requests_leave_nulls(db_session, monkeypatch):
    _credentials(monkeypatch)
    respx.post(opensky_live.TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok"}))
    respx.get(STATES).mock(return_value=httpx.Response(200, content=FIXTURE))
    calls = iter([httpx.Response(404), httpx.Response(403, text="You cannot access historical flights"),
                  httpx.Response(200, json={"not": "a list"}), httpx.ConnectError("x")])

    def answer(request):
        try:
            outcome = next(calls)
        except StopIteration:
            outcome = httpx.Response(429)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    respx.get(url__startswith=FLIGHTS).mock(side_effect=answer)

    snapshot = await fetch_opensky_live(db_session)

    assert snapshot.status == SNAPSHOT_SUCCESS  # live counts still stored
    rows = (await db_session.execute(select(AirportTrafficLive))).scalars().all()
    assert all(r.arrivals_last_24h is None and r.departures_last_24h is None for r in rows)


@respx.mock
async def test_failed_token_falls_back_to_anonymous(db_session, monkeypatch):
    _credentials(monkeypatch)
    respx.post(opensky_live.TOKEN_URL).mock(return_value=httpx.Response(401))
    states = respx.get(STATES).mock(return_value=httpx.Response(200, content=FIXTURE))
    flights = respx.get(url__startswith=FLIGHTS)

    snapshot = await fetch_opensky_live(db_session)

    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.details["authenticated"] is False
    assert "authorization" not in states.calls[0].request.headers and not flights.called


@respx.mock
async def test_token_response_without_access_token_is_anonymous(db_session, monkeypatch):
    _credentials(monkeypatch)
    respx.post(opensky_live.TOKEN_URL).mock(return_value=httpx.Response(200, json={}))
    respx.get(STATES).mock(return_value=httpx.Response(200, content=FIXTURE))
    snapshot = await fetch_opensky_live(db_session)
    assert snapshot.details["authenticated"] is False


@respx.mock
async def test_supplied_client_is_not_closed(db_session):
    respx.get(STATES).mock(return_value=httpx.Response(200, content=FIXTURE))
    async with httpx.AsyncClient() as client:
        snapshot = await fetch_opensky_live(db_session, client=client)
        assert not client.is_closed
    assert snapshot.status == SNAPSHOT_SUCCESS


# ---- API ----

def _client(db_session) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@respx.mock
async def test_api_live_and_history(db_session):
    async with _client(db_session) as client:
        empty = (await client.get("/api/datasets/air-traffic/live")).json()
        assert empty == {"taken_at": None, "india": None, "airports": []}

        respx.get(STATES).mock(return_value=httpx.Response(200, content=FIXTURE))
        await fetch_opensky_live(db_session)
        body = (await client.get("/api/datasets/air-traffic/live")).json()
        assert body["india"]["aircraft_over_india"] > 100 and len(body["airports"]) == 32
        delhi = next(a for a in body["airports"] if a["airport"] == "DEL")
        assert delhi["live_congestion"] in {"LOW", "MODERATE", "HIGH"} and delhi["icao"] == "VIDP"

        history = (await client.get("/api/datasets/air-traffic/history?airport=del&limit=5")).json()
        assert len(history) == 1 and history[0]["airport"] == "DEL"
        totals = (await client.get("/api/datasets/air-traffic/history")).json()
        assert totals[0]["aircraft_over_india"] == body["india"]["aircraft_over_india"]
        assert (await client.get("/api/datasets/air-traffic/history?airport=ZZZ")).status_code == 422
        assert (await client.get("/api/datasets/air-traffic/history?limit=0")).status_code == 422


# ---- evidence ----

def _request(route="DEL-BOM"):
    return EvidenceRequest(agent_type="NETWORK", objective="traffic now", route=route, previous_results=[])


async def test_evidence_empty_without_data(db_session):
    assert await live_air_traffic(db_session, _request()) == []


@respx.mock
async def test_evidence_for_a_route_and_without_one(db_session):
    respx.get(STATES).mock(return_value=httpx.Response(200, content=FIXTURE))
    snapshot = await fetch_opensky_live(db_session)

    (item,) = await live_air_traffic(db_session, _request())
    assert item.source == "opensky" and item.kind == "dataset" and item.reliability == 0.75
    assert item.id == f"traffic:opensky:DEL-BOM:{int(TAKEN_AT.timestamp())}"
    assert item.fetched_at == snapshot.fetched_at
    assert set(item.content["airports"]) == {"DEL", "BOM"} and item.content["route"] == "DEL-BOM"
    assert {"aircraft_within_radius", "live_congestion", "arrivals_last_24h", "departures_last_24h"} <= set(
        item.content["airports"]["DEL"]
    )

    (overall,) = await live_air_traffic(db_session, _request(route=None))
    assert overall.id.startswith("traffic:opensky:IN:") and "airports" not in overall.content
    assert overall.content["india"]["aircraft_over_india"] > 0

    (unknown,) = await live_air_traffic(db_session, _request("XXX-YYY"))
    assert unknown.content["airports"] == {}


async def test_evidence_without_dataset_snapshot_uses_taken_at(db_session):
    db_session.add(AirTrafficSnapshot(taken_at=TAKEN_AT, aircraft_over_india=3, airborne=2, on_ground=1))
    await db_session.flush()
    (item,) = await live_air_traffic(db_session, _request(None))
    assert item.fetched_at == TAKEN_AT
    assert (await db_session.execute(select(DatasetSnapshot))).scalars().all() == []

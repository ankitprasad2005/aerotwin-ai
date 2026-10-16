from datetime import date, timedelta

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.datasets import router
from app.api.deps import get_db
from app.models.external import SNAPSHOT_FAILED, WeatherForecast, WeatherObservation
from tests.weather_data import OBSERVED_AT, add_weather, make_snapshot


def _client(db_session) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_weather_without_data_lists_every_twin_airport_as_unknown(db_session):
    async with _client(db_session) as client:
        response = await client.get("/api/datasets/weather")

    body = response.json()
    assert response.status_code == 200
    assert [w["airport"] for w in body] == ["BOM", "DEL", "BLR", "MAA", "HYD", "CCU"]
    assert [w["icao"] for w in body] == ["VABB", "VIDP", "VOBL", "VOMM", "VOHS", "VECC"]
    for entry in body:
        assert entry["flight_category"] == "UNKNOWN" and entry["forecast"] == []
        assert all(entry[k] is None for k in ("observed_at", "wind_kt", "gust_kt", "visibility_sm", "ceiling_ft", "raw_text"))


async def test_weather_returns_the_latest_observation_and_the_latest_snapshots_forecast(db_session):
    await add_weather(
        db_session,
        observations={"BOM": dict(flight_category="IFR", wind_kt=12.0, gust_kt=22.0, visibility_sm=1.5, ceiling_ft=800.0)},
        forecasts={"BOM": {2: (30.0, 65.0, 95)}},
    )
    # An older observation is ignored, and a forecast day that only an older snapshot knows is not shown.
    old_snapshot = make_snapshot("open_meteo", minutes=-60)
    db_session.add(old_snapshot)
    await db_session.flush()
    db_session.add_all([
        WeatherObservation(
            airport="BOM", icao="VABB", observed_at=OBSERVED_AT - timedelta(hours=1), flight_category="VFR",
            wind_kt=1.0, raw_text="old",
        ),
        WeatherForecast(
            airport="BOM", forecast_date=date(2026, 10, 1), precipitation_mm=0, max_gust_kmh=0, weather_code=0,
            thunderstorm=False, snapshot_id=old_snapshot.id,
        ),
    ])
    await db_session.flush()

    async with _client(db_session) as client:
        body = (await client.get("/api/datasets/weather")).json()

    bom, delhi = body[0], body[1]
    assert bom["flight_category"] == "IFR" and bom["wind_kt"] == 12.0 and bom["gust_kt"] == 22.0
    assert bom["visibility_sm"] == 1.5 and bom["ceiling_ft"] == 800.0 and bom["raw_text"] == "METAR VABB 161100Z"
    assert bom["observed_at"].startswith("2026-10-16T11:00:00")
    assert [f["date"] for f in bom["forecast"]] == [f"2026-10-{d}" for d in range(16, 23)]
    assert bom["forecast"][2] == {
        "date": "2026-10-18", "precipitation_mm": 30.0, "max_gust_kmh": 65.0, "weather_code": 95, "thunderstorm": True,
    }
    assert set(bom) == {
        "airport", "icao", "observed_at", "flight_category", "wind_kt", "gust_kt", "visibility_sm", "ceiling_ft",
        "raw_text", "forecast", "taf_worst_flight_category_24h", "taf_thunderstorm_24h",
    }
    assert delhi["flight_category"] == "UNKNOWN" and delhi["forecast"] == []


async def test_weather_ignores_a_failed_forecast_snapshot(db_session):
    await add_weather(db_session, forecasts={"BOM": {}})
    db_session.add(make_snapshot("open_meteo", minutes=30, status=SNAPSHOT_FAILED))
    await db_session.flush()

    async with _client(db_session) as client:
        body = (await client.get("/api/datasets/weather")).json()

    assert len(body[0]["forecast"]) == 7

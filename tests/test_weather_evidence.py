import pytest

from app.agents.registry import AGENT_REGISTRY
from app.datasets import weather
from app.datasets.evidence import weather_forecast, weather_observation
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.catalog import EVIDENCE_PROVIDERS
from app.evidence.reliability import SOURCE_RELIABILITY
from tests.weather_data import add_weather, make_snapshot


def _request(route=None):
    return EvidenceRequest(agent_type="WEATHER", objective="x", route=route, previous_results=[])


def test_sources_have_the_documented_reliability():
    assert SOURCE_RELIABILITY["aviation_weather"] == 0.9
    assert SOURCE_RELIABILITY["open_meteo"] == 0.8


def test_providers_are_registered_and_used_by_the_weather_agent():
    assert EVIDENCE_PROVIDERS["weather_observation"] is weather_observation
    assert EVIDENCE_PROVIDERS["weather_forecast"] is weather_forecast
    assert AGENT_REGISTRY["WEATHER"].evidence_providers == ("weather_observation", "weather_forecast", "web_search")
    assert AGENT_REGISTRY["WEATHER"].depends_on == ("NETWORK",)


async def test_providers_return_nothing_without_data(db_session):
    assert await weather_observation(db_session, _request()) == []
    assert await weather_observation(db_session, _request("BOM-DEL")) == []
    assert await weather_forecast(db_session, _request()) == []
    assert await weather_forecast(db_session, _request("BOM-DEL")) == []


async def _seed(db_session):
    await add_weather(
        db_session,
        observations={
            "BOM": dict(flight_category="IFR", wind_kt=9.0, gust_kt=18.0, visibility_sm=1.86, ceiling_ft=700.0),
            "DEL": "MVFR",
            "BLR": "VFR",
        },
        forecasts={"BOM": {1: (2.0, 30.0, 95)}, "DEL": {3: (25.0, 10.0, 65)}, "BLR": {}},
    )


async def test_observation_items_for_the_routes_two_airports(db_session):
    await _seed(db_session)

    items = await weather_observation(db_session, _request("BOM-DEL"))

    assert [i.id for i in items] == ["metar:BOM:2026-10-16T11:00Z", "metar:DEL:2026-10-16T11:00Z"]
    bom = items[0]
    assert isinstance(bom, EvidenceItem)
    assert bom.source == "aviation_weather" and bom.kind == "dataset" and bom.reliability == 0.9
    assert bom.url == weather.metar_url() and bom.fetched_at is not None
    assert bom.content == {
        "airport": "BOM", "icao": "VABB", "observed_at": "2026-10-16T11:00:00+00:00", "flight_category": "IFR",
        "wind_kt": 9.0, "gust_kt": 18.0, "visibility_sm": 1.86, "ceiling_ft": 700.0, "raw_text": "METAR VABB 161100Z",
    }


async def test_observation_items_cover_all_airports_without_a_route_and_skip_unknown_ones(db_session):
    await _seed(db_session)

    everything = await weather_observation(db_session, _request())
    unknown_airport = await weather_observation(db_session, _request("XXX-YYY"))
    partly_known = await weather_observation(db_session, _request("BOM-HYD"))

    assert [i.content["airport"] for i in everything] == ["BOM", "DEL", "BLR"]  # only airports with observations
    assert unknown_airport == []
    assert [i.content["airport"] for i in partly_known] == ["BOM"]


async def test_forecast_items_for_the_routes_two_airports(db_session):
    await _seed(db_session)

    items = await weather_forecast(db_session, _request("BOM-DEL"))

    assert [i.id for i in items] == ["forecast:BOM:2026-10-16", "forecast:DEL:2026-10-16"]
    bom = items[0]
    assert bom.source == "open_meteo" and bom.reliability == 0.8 and bom.url == weather.forecast_url()
    assert bom.fetched_at is not None
    assert bom.content["airport"] == "BOM" and bom.content["thunderstorm_days"] == 1
    assert bom.content["disruption_days"] == 1 and bom.content["max_precipitation_mm"] == 2.0
    assert bom.content["max_gust_kmh"] == 30.0
    assert len(bom.content["days"]) == 7
    assert bom.content["days"][1] == {
        "date": "2026-10-17", "precipitation_mm": 2.0, "max_gust_kmh": 30.0, "weather_code": 95, "thunderstorm": True,
    }
    assert items[1].content["disruption_days"] == 1  # 25 mm of rain


async def test_forecast_items_without_a_route_cover_every_airport_with_a_forecast(db_session):
    await _seed(db_session)

    items = await weather_forecast(db_session, _request())

    assert [i.content["airport"] for i in items] == ["BOM", "DEL", "BLR"]


async def test_forecast_ignores_airports_outside_the_stations(db_session):
    await _seed(db_session)
    db_session.add(make_snapshot("open_meteo", minutes=5, status="FAILED"))
    await db_session.flush()

    assert await weather_forecast(db_session, _request("BOM-ZZZ")) != []
    assert [i.content["airport"] for i in await weather_forecast(db_session, _request("BOM-ZZZ"))] == ["BOM"]


@pytest.mark.parametrize("provider", [weather_observation, weather_forecast])
async def test_malformed_route_falls_back_to_all_airports(db_session, provider):
    await _seed(db_session)

    assert len(await provider(db_session, _request("garbage"))) == 3

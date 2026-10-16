import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from app.datasets import common, weather
from app.datasets.common import DatasetError
from app.datasets.weather import (
    fetch_aviation_weather, fetch_open_meteo, flight_category_for, forecast_url, metar_url, parse_metar, parse_open_meteo,
)
from tests import weather_mocks
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, WeatherForecast, WeatherObservation

FIXTURES = Path(__file__).parent / "fixtures" / "datasets"
METAR = (FIXTURES / "aviation_weather_metar.json").read_bytes()
FORECAST = (FIXTURES / "open_meteo_forecast.json").read_bytes()


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


def _entry(**o):
    base = {"icaoId": "VABB", "obsTime": 1792148400, "wspd": 9, "visib": 6, "clouds": [], "rawOb": "METAR VABB", "fltCat": "VFR"}
    base.update(o)
    return base


def _metar(*entries):
    return json.dumps(list(entries)).encode()


def test_station_mapping_covers_the_twin_airports():
    from app.datasets.common import TWIN_AIRPORTS

    assert set(weather.AIRPORT_STATIONS) == TWIN_AIRPORTS
    assert {i: s[0] for i, s in weather.AIRPORT_STATIONS.items()} == {
        "BOM": "VABB", "DEL": "VIDP", "BLR": "VOBL", "MAA": "VOMM", "HYD": "VOHS", "CCU": "VECC",
    }


def test_urls():
    assert metar_url() == "https://aviationweather.gov/api/data/metar?ids=VABB,VIDP,VOBL,VOMM,VOHS,VECC&format=json"
    url = forecast_url()
    assert url.startswith("https://api.open-meteo.com/v1/forecast?latitude=19.0887,28.5665,")
    assert "timezone=Asia%2FKolkata&forecast_days=7" in url


@pytest.mark.parametrize(
    "ceiling,visibility,expected",
    [
        (None, None, None),
        (None, 10, "VFR"), (3001, 6, "VFR"), (None, 5.1, "VFR"),
        (3000, 10, "MVFR"), (1000, 10, "MVFR"), (None, 5, "MVFR"), (None, 3, "MVFR"),
        (999, 10, "IFR"), (500, 10, "IFR"), (None, 2.99, "IFR"), (None, 1, "IFR"),
        (499, 10, "LIFR"), (None, 0.9, "LIFR"), (2000, 0.5, "LIFR"), (800, 4, "IFR"),
        (2500, None, "MVFR"), (400, None, "LIFR"),
    ],
)
def test_flight_category_thresholds(ceiling, visibility, expected):
    assert flight_category_for(ceiling, visibility) == expected


def test_parse_metar_real_response():
    rows = {r["airport"]: r for r in parse_metar(METAR)}
    assert set(rows) == set(weather.AIRPORT_STATIONS)
    bom = rows["BOM"]
    assert bom["icao"] == "VABB" and bom["flight_category"] == "IFR" and bom["wind_kt"] == 9
    assert bom["visibility_sm"] == 1.86 and bom["ceiling_ft"] is None and bom["gust_kt"] is None
    assert bom["observed_at"] == datetime.fromtimestamp(1792148400, tz=timezone.utc)
    assert bom["raw_text"].startswith("METAR VABB")
    assert rows["BLR"]["ceiling_ft"] == 8000  # lowest BKN/OVC layer; SCT and FEW layers are not a ceiling


def test_parse_metar_computes_the_category_when_the_source_has_none():
    rows = parse_metar(_metar(
        _entry(fltCat=None, visib=2, clouds=[{"cover": "OVC", "base": 700}, {"cover": "BKN", "base": 900}]),
        _entry(icaoId="VIDP", fltCat="WEIRD", visib="10+"),
    ))
    by = {r["airport"]: r for r in rows}
    assert by["BOM"]["flight_category"] == "IFR" and by["BOM"]["ceiling_ft"] == 700
    assert by["DEL"]["flight_category"] == "VFR" and by["DEL"]["visibility_sm"] == 10


def test_parse_metar_keeps_the_latest_report_and_skips_unusable_entries():
    rows = parse_metar(_metar(
        _entry(obsTime=1000, rawOb="old"),
        _entry(obsTime=2000, rawOb="new", wgst=25),
        _entry(obsTime=1500, rawOb="middle"),
        _entry(icaoId="EGLL"),  # not a twin airport
        _entry(icaoId="VOBL", rawOb=""),  # no raw text
        _entry(icaoId="VOMM", obsTime=None, reportTime="nonsense"),
        _entry(icaoId="VOHS", fltCat=None, visib=None, clouds=[]),  # nothing to categorise
        _entry(icaoId="VECC", obsTime=None, reportTime="2026-10-16T11:00:00.000Z", wspd=None, visib="x", fltCat="LIFR"),
        "junk",
    ))
    by = {r["airport"]: r for r in rows}
    assert set(by) == {"BOM", "CCU"}
    assert by["BOM"]["raw_text"] == "new" and by["BOM"]["gust_kt"] == 25
    assert by["CCU"]["observed_at"] == datetime(2026, 10, 16, 11, tzinfo=timezone.utc)
    assert by["CCU"]["wind_kt"] == 0.0 and by["CCU"]["visibility_sm"] is None


@pytest.mark.parametrize("junk", [b"", b"<html>", b'{"a": 1}'])
def test_parse_metar_rejects_malformed_documents(junk):
    with pytest.raises(DatasetError, match="malformed"):
        parse_metar(junk)


def test_parse_open_meteo_real_response():
    rows = parse_open_meteo(FORECAST)
    assert len(rows) == 6 * 7
    assert [r["airport"] for r in rows[:7]] == ["BOM"] * 7
    first = rows[0]
    assert first["forecast_date"] == date(2026, 10, 16) and first["weather_code"] == 3
    assert first["precipitation_mm"] == 0.0 and first["max_gust_kmh"] == 27.0 and first["thunderstorm"] is False


def _om(daily, n=6):
    return json.dumps([{"daily": daily}] * n).encode()


def test_parse_open_meteo_flags_thunderstorm_codes_and_skips_bad_days():
    daily = {
        "time": ["2026-10-16", "2026-10-17", "2026-10-18", "2026-10-19", "bad-date", "2026-10-21", "2026-10-22"],
        "precipitation_sum": [1.0, 2.0, 3.0, None, 5.0, 6.0, 7.0],
        "wind_gusts_10m_max": [10, 20, 30, 40, 50, 60, 70],
        "weather_code": [95, 96, 99, 1, 3, 80, 0],
    }
    rows = [r for r in parse_open_meteo(_om(daily)) if r["airport"] == "BOM"]
    assert [r["forecast_date"].day for r in rows] == [16, 17, 18, 21, 22]
    assert [r["thunderstorm"] for r in rows] == [True, True, True, False, False]


@pytest.mark.parametrize("payload", [b"", b"[]", b'{"daily": {}}', b'[{"x": 1}]'])
def test_parse_open_meteo_rejects_malformed_documents(payload):
    with pytest.raises(DatasetError, match="malformed"):
        parse_open_meteo(payload)


@respx.mock
async def test_fetch_aviation_weather_upserts_observations(db_session, tmp_path):
    weather_mocks.mock_list_batches(weather.metar_urls(), METAR)

    snap = await fetch_aviation_weather(db_session, base_dir=tmp_path)
    again = await fetch_aviation_weather(db_session, base_dir=tmp_path)  # idempotent

    assert snap.status == again.status == SNAPSHOT_SUCCESS and snap.row_count == 6
    assert snap.source == "aviation_weather" and snap.details["airports"] == sorted(weather.AIRPORT_STATIONS)
    assert json.loads(Path(snap.local_path).read_bytes()) == json.loads(METAR)
    stored = (await db_session.execute(select(WeatherObservation))).scalars().all()
    assert len(stored) == 6 and all(o.snapshot_id == again.id for o in stored)


@respx.mock
@pytest.mark.parametrize("response", [httpx.Response(500), httpx.Response(200, content=b"[]"), httpx.Response(200, content=b"nope")])
async def test_fetch_aviation_weather_failure_is_a_failed_snapshot_with_no_rows(db_session, tmp_path, response):
    weather_mocks.mock_all_batches(weather.metar_urls(), response)

    snap = await fetch_aviation_weather(db_session, base_dir=tmp_path)

    assert snap.status == SNAPSHOT_FAILED and snap.row_count == 0
    assert (await db_session.execute(select(WeatherObservation))).scalars().all() == []


@respx.mock
async def test_fetch_open_meteo_upserts_forecasts(db_session, tmp_path):
    weather_mocks.mock_forecast()

    snap = await fetch_open_meteo(db_session, base_dir=tmp_path)
    again = await fetch_open_meteo(db_session, base_dir=tmp_path)

    assert snap.status == again.status == SNAPSHOT_SUCCESS and snap.row_count == 128 * 7
    assert snap.source == "open_meteo" and snap.details == {"first_date": "2026-10-16", "last_date": "2026-10-22"}
    assert len((await db_session.execute(select(WeatherForecast))).scalars().all()) == 128 * 7


@respx.mock
@pytest.mark.parametrize("response", [
    httpx.Response(503),
    httpx.Response(200, content=b"{}"),
    httpx.Response(200, content=_om({"time": [], "precipitation_sum": [], "wind_gusts_10m_max": [], "weather_code": []})),
])
async def test_fetch_open_meteo_failure_is_a_failed_snapshot(db_session, tmp_path, response):
    weather_mocks.mock_all_batches(weather.forecast_urls(), response)

    snap = await fetch_open_meteo(db_session, base_dir=tmp_path)

    assert snap.status == SNAPSHOT_FAILED and snap.row_count == 0
    assert (await db_session.execute(select(WeatherForecast))).scalars().all() == []

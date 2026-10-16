import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from app.datasets import common, weather
from app.datasets.common import DatasetError
from app.datasets.weather import fetch_taf, has_thunderstorm, parse_taf, taf_url
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, WeatherTaf

TAF = (Path(__file__).parent / "fixtures" / "datasets" / "aviation_weather_taf.json").read_bytes()
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
EPOCH = int(NOW.timestamp())
HOUR = 3600


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


def _period(start_h, end_h, visib=6.0, clouds=None, wx=None, change=None):
    return {
        "timeFrom": EPOCH + start_h * HOUR, "timeTo": EPOCH + end_h * HOUR, "fcstChange": change,
        "visib": visib, "clouds": clouds or [], "wxString": wx,
    }


def _taf(*periods, icao="VABB", issued="2026-10-16T11:00:00.000Z", valid_hours=30, raw="TAF VABB 161100Z"):
    return {
        "icaoId": icao, "issueTime": issued, "validTimeFrom": EPOCH, "validTimeTo": EPOCH + valid_hours * HOUR,
        "rawTAF": raw, "fcsts": list(periods),
    }


def _parse(*entries):
    return parse_taf(json.dumps(list(entries)).encode(), NOW)


def test_taf_url():
    assert taf_url() == "https://aviationweather.gov/api/data/taf?ids=VABB,VIDP,VOBL,VOMM,VOHS,VECC&format=json"


@pytest.mark.parametrize(
    "wx,expected",
    [
        (None, False), ("", False), ("RA BR", False), ("NSW", False), ("TSRA", True), ("-TSRA RA", True), ("+TSRA", True),
        ("VCTS", True), ("TS", True), ("TSGR", True), ("FZRA", False), ("SHRA", False),
    ],
)
def test_has_thunderstorm(wx, expected):
    assert has_thunderstorm(wx) is expected


def test_parse_taf_on_the_real_fixture():
    rows = {r["airport"]: r for r in parse_taf(TAF, NOW)}

    assert set(rows) == {"BOM", "DEL", "BLR", "MAA", "HYD", "CCU"}
    assert {a: r["worst_flight_category_24h"] for a, r in rows.items()} == {
        "BOM": "IFR", "DEL": "IFR", "BLR": "LIFR", "MAA": "LIFR", "HYD": "MVFR", "CCU": "IFR",
    }
    assert {a: r["thunderstorm_24h"] for a, r in rows.items()} == {
        "BOM": False, "DEL": False, "BLR": False, "MAA": True, "HYD": False, "CCU": False,
    }
    bom = rows["BOM"]
    assert bom["icao"] == "VABB" and bom["issued_at"] == datetime(2026, 10, 16, 11, 0, tzinfo=timezone.utc)
    assert bom["valid_from"] == datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    assert bom["valid_to"] == datetime(2026, 10, 17, 18, 0, tzinfo=timezone.utc)
    assert bom["raw_text"].startswith("TAF COR VABB 161100Z")


def test_only_periods_in_the_next_24_hours_count():
    rows = _parse(
        _taf(
            _period(0, 6, visib=6.0),
            _period(6, 24, visib=6.0),
            _period(24, 30, visib=0.4, wx="TSRA"),  # starts exactly at the end of the window: excluded
        )
    )
    assert rows[0]["worst_flight_category_24h"] == "VFR" and rows[0]["thunderstorm_24h"] is False

    rows = _parse(_taf(_period(-10, -1, visib=0.4, wx="TS"), _period(-1, 5, visib=6.0)))  # the first one is over
    assert rows[0]["worst_flight_category_24h"] == "VFR" and rows[0]["thunderstorm_24h"] is False

    rows = _parse(_taf(_period(0, 30, visib=6.0), _period(23, 25, visib=0.4, wx="TS", change="TEMPO")))  # overlaps the end
    assert rows[0]["worst_flight_category_24h"] == "LIFR" and rows[0]["thunderstorm_24h"] is True


def test_the_worst_category_wins_and_is_computed_with_the_metar_thresholds():
    ceiling = [{"cover": "BKN", "base": 400}]
    rows = _parse(_taf(_period(0, 5, visib=6.0), _period(5, 10, visib=4.0), _period(10, 15, visib=6.0, clouds=ceiling)))
    assert rows[0]["worst_flight_category_24h"] == "LIFR"  # ceiling 400 ft
    rows = _parse(_taf(_period(0, 5, visib=6.0), _period(5, 10, visib=4.0)))
    assert rows[0]["worst_flight_category_24h"] == "MVFR"
    rows = _parse(_taf(_period(0, 5, visib=2.0, clouds=[{"cover": "FEW", "base": 100}])))  # FEW is no ceiling
    assert rows[0]["worst_flight_category_24h"] == "IFR"


def test_periods_without_visibility_or_ceiling_are_ignored_and_a_taf_without_any_is_skipped():
    rows = _parse(_taf(_period(0, 5, visib=None), _period(5, 10, visib=6.0)))
    assert rows[0]["worst_flight_category_24h"] == "VFR"
    assert _parse(_taf(_period(0, 5, visib=None))) == []
    assert _parse(_taf(_period(30, 40, visib=6.0))) == []  # nothing in the next 24 hours


def test_the_latest_issue_of_an_airport_wins_and_unusable_entries_are_skipped():
    older = _taf(_period(0, 5, visib=6.0), issued="2026-10-16T05:00:00.000Z", raw="OLD")
    newer = _taf(_period(0, 5, visib=1.5), issued="2026-10-16T11:00:00.000Z", raw="NEW")
    other_airport = _taf(_period(0, 5, visib=6.0), icao="EGLL")
    bad = [
        "junk", {**newer, "icaoId": "VIDP", "rawTAF": ""}, {**newer, "icaoId": "VOBL", "issueTime": "never"},
        {**newer, "icaoId": "VOMM", "validTimeFrom": None}, {**newer, "icaoId": "VOHS", "fcsts": "x"},
        {**newer, "icaoId": "VECC", "fcsts": ["x", {"timeFrom": "a", "timeTo": 1}]},
    ]
    payload = json.dumps([older, newer, other_airport, *bad]).encode()

    rows = parse_taf(payload, NOW)

    assert [(r["airport"], r["raw_text"], r["worst_flight_category_24h"]) for r in rows] == [("BOM", "NEW", "IFR")]
    # An older issue arriving after the newer one does not replace it.
    rows = parse_taf(json.dumps([newer, older]).encode(), NOW)
    assert rows[0]["raw_text"] == "NEW"


@pytest.mark.parametrize("content", [b"not json", b'{"a": 1}', b'"x"'])
def test_parse_taf_rejects_malformed_responses(content):
    with pytest.raises(DatasetError):
        parse_taf(content, NOW)


@respx.mock
async def test_fetch_taf_stores_a_row_per_airport(db_session, tmp_path):
    route = respx.get(url__startswith=weather.TAF_API).mock(return_value=httpx.Response(200, content=TAF))

    snapshot = await fetch_taf(db_session, base_dir=tmp_path, now=NOW)

    assert route.call_count == 1 and route.calls[0].request.url.params["format"] == "json"
    assert snapshot.source == "aviation_weather_taf" and snapshot.status == SNAPSHOT_SUCCESS and snapshot.row_count == 6
    rows = (await db_session.execute(select(WeatherTaf))).scalars().all()
    assert {r.airport: r.thunderstorm_24h for r in rows}["MAA"] is True
    assert all(r.snapshot_id == snapshot.id for r in rows)
    assert (tmp_path / "aviation_weather_taf" / "2026-10-16" / "taf.json").read_bytes() == TAF

    again = await fetch_taf(db_session, base_dir=tmp_path, now=NOW)  # same TAF issue: updated in place
    assert again.status == SNAPSHOT_SUCCESS
    assert len((await db_session.execute(select(WeatherTaf))).scalars().all()) == 6


@respx.mock
async def test_fetch_taf_failures_are_failed_snapshots(db_session, tmp_path):
    respx.get(url__startswith=weather.TAF_API).mock(return_value=httpx.Response(503))
    failed = await fetch_taf(db_session, base_dir=tmp_path, now=NOW)
    assert failed.status == SNAPSHOT_FAILED and failed.row_count == 0

    respx.get(url__startswith=weather.TAF_API).mock(return_value=httpx.Response(200, content=b"[]"))
    empty = await fetch_taf(db_session, base_dir=tmp_path, now=NOW)
    assert empty.status == SNAPSHOT_FAILED and "no usable TAF" in empty.error
    assert (await db_session.execute(select(WeatherTaf))).scalars().all() == []

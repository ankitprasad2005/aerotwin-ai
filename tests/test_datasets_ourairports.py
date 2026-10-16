from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from app.datasets import common, ourairports
from app.datasets.common import DatasetError
from app.datasets.ourairports import (
    AIRPORTS_URL, FREQUENCIES_URL, RUNWAYS_URL, count_frequencies, fetch_ourairports, parse_airports, parse_ourairports,
    parse_runways,
)
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, IndiaAirport, IndiaRunway

FIXTURES = Path(__file__).parent / "fixtures" / "ourairports"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


@pytest.fixture
def datasets_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "get_settings", lambda: type("S", (), {"datasets_dir": str(tmp_path)})())
    return tmp_path


def _mock(*, airports=None, runways=None, frequencies=None):
    respx.get(AIRPORTS_URL).mock(return_value=httpx.Response(200, content=airports or _read("airports.csv")))
    respx.get(RUNWAYS_URL).mock(return_value=httpx.Response(200, content=runways or _read("runways.csv")))
    respx.get(FREQUENCIES_URL).mock(return_value=httpx.Response(200, content=frequencies or _read("airport-frequencies.csv")))


def test_parse_airports_keeps_only_india_and_maps_the_fields():
    airports = {a["ident"]: a for a in parse_airports(_read("airports.csv"))}

    assert set(airports) == {
        "VAAH", "VABB", "VAPO", "VECC", "VEGT", "VIDP", "VOBL", "VOHS", "VOMM", "VOPB", "VOPN", "IN-0012", "IN-0005", "HU-0072",
    }
    mumbai = airports["VABB"]
    assert mumbai["icao_code"] == "VABB" and mumbai["iata_code"] == "BOM"
    assert mumbai["name"] == "Chhatrapati Shivaji Maharaj International Airport" and mumbai["municipality"] == "Mumbai"
    assert mumbai["airport_type"] == "large_airport" and mumbai["scheduled_service"] is True
    assert (mumbai["latitude_deg"], mumbai["longitude_deg"], mumbai["elevation_ft"]) == (19.088699, 72.867897, 39.0)
    assert airports["VOPN"]["scheduled_service"] is False
    # Closed strips and heliports are kept too ("all Indian airports"); a missing elevation stays empty.
    assert airports["IN-0005"]["airport_type"] == "closed" and airports["IN-0005"]["elevation_ft"] is None
    assert airports["IN-0005"]["iata_code"] is None and airports["IN-0005"]["icao_code"] is None
    assert airports["HU-0072"]["airport_type"] == "heliport"


def test_parse_airports_derives_the_icao_code_from_a_four_letter_ident():
    csv_text = (
        "id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,iso_country,iso_region,municipality,"
        "scheduled_service,icao_code,iata_code\n"
        "1,VAXX,small_airport,Xx,1,2,3,AS,IN,IN-GJ,Xx,no,,\n"
        "2,IN-0099,small_airport,Yy,x,y,,AS,IN,IN-GJ,,no,,\n"
        "3,,small_airport,No ident,1,2,3,AS,IN,IN-GJ,,no,,\n"
    )
    airports = {a["ident"]: a for a in parse_airports(csv_text.encode())}

    assert set(airports) == {"VAXX", "IN-0099"}
    assert airports["VAXX"]["icao_code"] == "VAXX"
    assert airports["IN-0099"]["icao_code"] is None and airports["IN-0099"]["latitude_deg"] is None


def test_parse_runways_and_frequencies():
    idents = {a["ident"] for a in parse_airports(_read("airports.csv"))}
    runways = parse_runways(_read("runways.csv"), idents)

    assert {r["airport_ident"] for r in runways} <= idents
    mumbai = sorted((r for r in runways if r["airport_ident"] == "VABB"), key=lambda r: -r["length_ft"])
    assert len(mumbai) == 2 and mumbai[0]["length_ft"] == 11511.0 and mumbai[0]["surface"]
    assert mumbai[0]["lighted"] is True and mumbai[0]["closed"] is False
    assert {mumbai[0]["le_ident"], mumbai[0]["he_ident"]} == {"09", "27"}
    assert parse_runways(_read("runways.csv"), set()) == []
    counts = count_frequencies(_read("airport-frequencies.csv"))
    assert counts["26434"] > 5  # Mumbai


def test_parse_ourairports_attaches_the_frequency_count():
    airports, runways = parse_ourairports(_read("airports.csv"), _read("runways.csv"), _read("airport-frequencies.csv"))

    by_ident = {a["ident"]: a for a in airports}
    assert by_ident["VABB"]["frequency_count"] > 5 and by_ident["IN-0005"]["frequency_count"] == 0
    assert all("_ref" not in a for a in airports)
    assert len(runways) == 20


@pytest.mark.parametrize(
    "kind, content, message",
    [
        ("airports", b"id,ident\n1,X\n", "missing columns"),
        ("airports", b"id,ident,type,name,iso_country\n1,KJFK,large_airport,JFK,US\n", "no Indian airports"),
    ],
)
def test_parse_ourairports_rejects_a_changed_or_empty_file(kind, content, message):
    with pytest.raises(DatasetError, match=message):
        parse_ourairports(content, _read("runways.csv"), _read("airport-frequencies.csv"))


@respx.mock
async def test_fetch_stores_airports_and_runways(db_session, datasets_tmp):
    _mock()

    snapshot = await fetch_ourairports(db_session)

    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.source_url == AIRPORTS_URL
    assert snapshot.details == {"airports": 14, "runways": 20} and snapshot.row_count == 34
    assert snapshot.checksum and Path(snapshot.local_path).exists()
    airports = (await db_session.execute(select(IndiaAirport))).scalars().all()
    assert len(airports) == 14 and all(a.snapshot_id == snapshot.id for a in airports)
    delhi = next(a for a in airports if a.ident == "VIDP")
    assert delhi.iata_code == "DEL" and delhi.scheduled_service is True and delhi.frequency_count > 0
    runways = (await db_session.execute(select(IndiaRunway).where(IndiaRunway.airport_ident == "VIDP"))).scalars().all()
    assert len(runways) == 4 and max(r.length_ft for r in runways) > 12000


@respx.mock
async def test_fetch_twice_updates_in_place(db_session, datasets_tmp):
    _mock()
    await fetch_ourairports(db_session)
    await fetch_ourairports(db_session)

    assert len((await db_session.execute(select(IndiaAirport))).scalars().all()) == 14
    assert len((await db_session.execute(select(IndiaRunway))).scalars().all()) == 20


@respx.mock
async def test_fetch_fails_when_a_download_fails(db_session, datasets_tmp):
    _mock()
    respx.get(RUNWAYS_URL).mock(return_value=httpx.Response(500))

    snapshot = await fetch_ourairports(db_session)

    assert snapshot.status == SNAPSHOT_FAILED and "runways.csv" in snapshot.error
    assert (await db_session.execute(select(IndiaAirport))).scalars().all() == []


def test_source_name():
    assert ourairports.SOURCE == "ourairports_india"

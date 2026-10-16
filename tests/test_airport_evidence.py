from datetime import datetime, timezone

from app.datasets import aai_traffic, ourairports
from app.datasets.airport_evidence import airport_infrastructure, airport_throughput
from app.evidence import catalog
from app.evidence.base import EvidenceRequest
from app.models.external import (
    SNAPSHOT_SUCCESS, AirportTrafficMonthly, DatasetSnapshot, IndiaAirport, IndiaRunway,
)

FETCHED = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)


def _request(route="BOM-DEL"):
    return EvidenceRequest(agent_type="NETWORK", objective="x", route=route, previous_results=[])


async def _seed_infrastructure(db):
    db.add(DatasetSnapshot(source=ourairports.SOURCE, fetched_at=FETCHED, status=SNAPSHOT_SUCCESS, source_url="https://x"))
    db.add_all(
        [
            IndiaAirport(
                ident="VABB", icao_code="VABB", iata_code="BOM", name="Chhatrapati Shivaji Maharaj International Airport",
                airport_type="large_airport", municipality="Mumbai", elevation_ft=39.0, scheduled_service=True, frequency_count=9,
            ),
            IndiaAirport(
                ident="VIDP", icao_code="VIDP", iata_code="DEL", name="Indira Gandhi International Airport",
                airport_type="large_airport", municipality="New Delhi", elevation_ft=777.0, scheduled_service=True, frequency_count=12,
            ),
            IndiaRunway(ourairports_id=1, airport_ident="VABB", length_ft=11511.0, width_ft=197.0, surface="ASP", lighted=True, closed=False, le_ident="09", he_ident="27"),
            IndiaRunway(ourairports_id=2, airport_ident="VABB", length_ft=9419.0, width_ft=148.0, surface="ASP", lighted=True, closed=False, le_ident="14", he_ident="32"),
            IndiaRunway(ourairports_id=3, airport_ident="VABB", length_ft=13000.0, width_ft=148.0, surface="ASP", lighted=False, closed=True, le_ident="05", he_ident=None),
            IndiaRunway(ourairports_id=4, airport_ident="VIDP", length_ft=None, width_ft=None, surface=None, lighted=False, closed=False, le_ident=None, he_ident=None),
        ]
    )
    await db.flush()


async def test_infrastructure_returns_nothing_without_data_or_route(db_session):
    assert await airport_infrastructure(db_session, _request()) == []
    await _seed_infrastructure(db_session)
    assert await airport_infrastructure(db_session, _request(None)) == []
    assert await airport_infrastructure(db_session, _request("BOM")) == []
    assert await airport_infrastructure(db_session, _request("XXX-YYY")) == []


async def test_infrastructure_describes_the_runways_of_both_airports(db_session):
    await _seed_infrastructure(db_session)

    items = await airport_infrastructure(db_session, _request())

    assert [i.id for i in items] == ["ourairports:BOM", "ourairports:DEL"]
    bom = items[0]
    assert bom.source == "ourairports" and bom.kind == "dataset" and bom.reliability == 0.8
    assert bom.fetched_at == FETCHED and bom.url == "https://ourairports.com/airports/VABB/"
    assert bom.title.startswith("BOM airport infrastructure")
    assert bom.content["icao"] == "VABB" and bom.content["elevation_ft"] == 39.0 and bom.content["city"] == "Mumbai"
    assert bom.content["runway_count"] == 3 and bom.content["open_runway_count"] == 2
    assert bom.content["longest_runway_ft"] == 11511.0  # the closed 13000 ft runway is ignored
    assert bom.content["longest_runway_m"] == 3509 and bom.content["frequency_count"] == 9
    assert bom.content["runways"][0] == {
        "designator": "05", "length_ft": 13000.0, "width_ft": 148.0, "surface": "ASP", "lighted": False, "closed": True,
    }
    del_ = items[1].content
    assert del_["longest_runway_ft"] is None and del_["longest_runway_m"] is None and del_["open_runway_count"] == 1


async def test_infrastructure_with_one_known_airport_and_no_snapshot(db_session):
    db_session.add(IndiaAirport(ident="VABB", icao_code="VABB", iata_code="BOM", name="Mumbai", airport_type="large_airport"))
    await db_session.flush()

    items = await airport_infrastructure(db_session, _request())

    assert [i.id for i in items] == ["ourairports:BOM"]
    assert items[0].fetched_at is None and items[0].content["runway_count"] == 0


def _traffic(name, iata, period, **extra):
    return AirportTrafficMonthly(airport_name=name, iata_code=iata, period=period, **extra)


async def test_throughput_returns_nothing_without_data_or_route(db_session):
    assert await airport_throughput(db_session, _request()) == []
    assert await airport_throughput(db_session, _request(None)) == []


async def test_throughput_uses_the_latest_month_of_each_airport(db_session):
    db_session.add(DatasetSnapshot(source=aai_traffic.SOURCE, fetched_at=FETCHED, status=SNAPSHOT_SUCCESS, source_url="https://x"))
    db_session.add_all(
        [
            _traffic("MUMBAI (MIAL)", "BOM", "2026-07", aircraft_movements=1, passengers=1, freight_tonnes=1.0),
            _traffic(
                "MUMBAI (MIAL)", "BOM", "2026-08", aircraft_movements=26017, passengers=4050443, freight_tonnes=81532.3,
                movements_domestic=18644, movements_international=7373, passengers_domestic=2784261,
                passengers_international=1266182, movements_yoy_pct=-5.1, passengers_yoy_pct=-10.4, freight_yoy_pct=7.6,
            ),
            _traffic("DELHI", "DEL", "2026-08", aircraft_movements=40160, passengers=6083616, freight_tonnes=106425.6),
        ]
    )
    await db_session.flush()

    items = await airport_throughput(db_session, _request())

    assert [i.id for i in items] == ["aai:BOM:2026-08", "aai:DEL:2026-08"]
    bom = items[0]
    assert bom.source == "aai_traffic" and bom.kind == "dataset" and bom.reliability == 0.9
    assert bom.fetched_at == FETCHED and bom.url == aai_traffic.INDEX_URL
    assert bom.content == {
        "airport": "BOM", "airport_name": "MUMBAI (MIAL)", "period": "2026-08", "aircraft_movements": 26017,
        "passengers": 4050443, "freight_tonnes": 81532.3, "movements_domestic": 18644, "movements_international": 7373,
        "passengers_domestic": 2784261, "passengers_international": 1266182, "movements_yoy_pct": -5.1,
        "passengers_yoy_pct": -10.4, "freight_yoy_pct": 7.6,
    }
    assert items[1].content["movements_yoy_pct"] is None


async def test_throughput_skips_an_airport_without_traffic_and_works_without_a_snapshot(db_session):
    db_session.add(_traffic("DELHI", "DEL", "2026-08", passengers=5))
    await db_session.flush()

    items = await airport_throughput(db_session, _request())

    assert [i.id for i in items] == ["aai:DEL:2026-08"] and items[0].fetched_at is None


async def test_without_a_route_the_providers_cover_every_airport_of_the_twin(db_session):
    from app.seed.seed import run_seed

    await run_seed(db_session)
    db_session.add_all(
        [
            _traffic("MUMBAI (MIAL)", "BOM", "2026-08", passengers=1),
            _traffic("DELHI", "DEL", "2026-08", passengers=2),
            _traffic("CHENNAI", "MAA", "2026-08", passengers=3),
            IndiaAirport(ident="VOBL", icao_code="VOBL", iata_code="BLR", name="Kempegowda", airport_type="large_airport"),
        ]
    )
    await db_session.flush()

    traffic = await airport_throughput(db_session, _request(None))
    infrastructure = await airport_infrastructure(db_session, _request(None))

    assert [i.id for i in traffic] == ["aai:BOM:2026-08", "aai:DEL:2026-08", "aai:MAA:2026-08"]
    assert [i.id for i in infrastructure] == ["ourairports:BLR"]


def test_providers_are_registered():
    assert catalog.EVIDENCE_PROVIDERS["airport_infrastructure"] is airport_infrastructure
    assert catalog.EVIDENCE_PROVIDERS["airport_throughput"] is airport_throughput

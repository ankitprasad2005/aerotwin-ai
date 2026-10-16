from datetime import date, timedelta

from app.agents.registry import AGENT_REGISTRY
from app.datasets import airworthiness, weather
from app.datasets.evidence import airworthiness_directives, weather_taf
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.catalog import EVIDENCE_PROVIDERS
from app.evidence.reliability import SOURCE_RELIABILITY
from app.seed.seed import run_seed
from tests.ad_taf_data import add_directives, add_tafs


def _request(route=None):
    return EvidenceRequest(agent_type="MAINTENANCE", objective="x", route=route, previous_results=[])


def test_reliability_and_registration():
    assert SOURCE_RELIABILITY["faa_airworthiness_directives"] == 0.95
    assert SOURCE_RELIABILITY["aviation_weather"] == 0.9
    assert EVIDENCE_PROVIDERS["airworthiness_directives"] is airworthiness_directives
    assert EVIDENCE_PROVIDERS["weather_taf"] is weather_taf
    assert "airworthiness_directives" in AGENT_REGISTRY["MAINTENANCE"].evidence_providers
    assert "airworthiness_directives" in AGENT_REGISTRY["FLEET"].evidence_providers
    assert "weather_taf" in AGENT_REGISTRY["WEATHER"].evidence_providers
    assert "recent_airworthiness_directives" in AGENT_REGISTRY["MAINTENANCE"].system_instructions
    for agent in ("MAINTENANCE", "FLEET"):
        assert "must not invent" in AGENT_REGISTRY[agent].system_instructions
    assert "taf_worst_flight_category_24h" in AGENT_REGISTRY["WEATHER"].system_instructions


async def test_providers_return_nothing_without_data(db_session):
    await run_seed(db_session)
    assert await airworthiness_directives(db_session, _request()) == []
    assert await weather_taf(db_session, _request()) == []
    assert await weather_taf(db_session, _request("BOM-DEL")) == []


async def test_one_item_per_fleet_type_newest_first(db_session):
    await run_seed(db_session)  # fleet: A320 (2), A321, B737
    await add_directives(
        db_session,
        *[(f"a{i}", 10 + i, ["A320"]) for i in range(7)],  # 7 A320 ADs, 10..16 days old
        ("both", 40, ["A320", "A321"]),
        ("b1", 5, ["B737"]),
        ("old", 500, ["A321"]),  # outside the 365 days
        ("other", 1, ["A380"]),  # not a fleet type
        {"document_number": "long", "publication_date": date.today() - timedelta(days=50), "aircraft_types": ["A321"],
         "abstract": "y" * 500},
    )

    items = await airworthiness_directives(db_session, _request())

    assert [i.id for i in items] == ["ad:B737", "ad:A320", "ad:A321"]  # newest directive first: 5, 10, 40 days old
    b737, a320, a321 = items
    assert isinstance(b737, EvidenceItem)
    assert b737.source == "faa_airworthiness_directives" and b737.kind == "dataset" and b737.reliability == 0.95
    assert b737.url == airworthiness.DOCS_URL and b737.fetched_at is not None
    assert b737.content["aircraft_type"] == "B737" and b737.content["count_last_365_days"] == 1
    assert b737.content["directives"] == [{
        "document_number": "b1", "title": "Airworthiness Directives; Airbus SAS Airplanes",
        "publication_date": (date.today() - timedelta(days=5)).isoformat(),
        "url": "https://www.federalregister.gov/d/b1", "summary": "The FAA is adopting a new AD for b1.",
    }]
    assert a320.content["count_last_365_days"] == 8
    assert [d["document_number"] for d in a320.content["directives"]] == ["a0", "a1", "a2", "a3", "a4"]  # the 5 newest
    assert a321.content["count_last_365_days"] == 2 and a321.content["directives"][0]["document_number"] == "both"
    assert len(a321.content["directives"][1]["summary"]) == 300


async def test_taf_items_for_the_routes_two_airports(db_session):
    await add_tafs(db_session, {"BOM": ("IFR", True), "DEL": ("VFR", False), "BLR": ("MVFR", False)})

    items = await weather_taf(db_session, _request("BOM-DEL"))

    assert [i.id for i in items] == ["taf:BOM:2026-10-16T11:00Z", "taf:DEL:2026-10-16T11:00Z"]
    bom = items[0]
    assert bom.source == "aviation_weather" and bom.kind == "dataset" and bom.reliability == 0.9
    assert bom.url == weather.taf_url() and bom.fetched_at is not None
    assert bom.content == {
        "airport": "BOM", "icao": "VABB", "issued_at": "2026-10-16T11:00:00+00:00",
        "valid_from": "2026-10-16T11:00:00+00:00", "valid_to": "2026-10-17T17:00:00+00:00",
        "worst_flight_category_24h": "IFR", "thunderstorm_24h": True, "raw_text": "TAF VABB 161100Z",
    }
    assert [i.content["airport"] for i in await weather_taf(db_session, _request())] == ["BOM", "DEL", "BLR"]
    assert await weather_taf(db_session, _request("MAA-CCU")) == []

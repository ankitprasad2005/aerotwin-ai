from datetime import date

from app.datasets import airport_charges, airport_charges_evidence
from app.datasets.airport_charges_evidence import airport_charges as provider
from app.evidence import catalog
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.reliability import SOURCE_RELIABILITY
from app.models.external import FxRate
from app.seed.seed import run_seed

DAY = date(2026, 10, 16)


def _request(route: str | None = "BOM-DEL", agent: str = "FINANCE") -> EvidenceRequest:
    return EvidenceRequest(agent_type=agent, objective="x", route=route, previous_results=[])


def test_registration_and_reliability():
    assert catalog.EVIDENCE_PROVIDERS["airport_charges"] is provider
    assert SOURCE_RELIABILITY["aera"] == 0.9
    assert "aera" in EvidenceItem.model_fields["source"].annotation.__args__


async def _prepare(db, monkeypatch, seed=True):
    monkeypatch.setattr(airport_charges_evidence, "_today", lambda: DAY)
    if seed:
        await run_seed(db)
    await airport_charges.fetch_airport_charges(db)
    db.add(FxRate(base="USD", quote="INR", rate_date=date(2026, 10, 16), rate=85.0))
    await db.flush()


async def test_the_item_for_a_route_has_both_airports_and_the_passenger_charges(db_session, monkeypatch):
    await _prepare(db_session, monkeypatch)

    [item] = await provider(db_session, _request("BOM-DEL"))

    assert item.id == "airport:BOM-DEL" and item.source == "aera" and item.kind == "dataset"
    assert item.reliability == 0.9 and item.url == "https://www.aera.gov.in/tariff-orders"
    assert item.fetched_at is not None
    assert "BOM-DEL" in item.title
    content = item.content
    assert content["route"] == "BOM-DEL" and content["aircraft_type"] == "A320"
    assert content["origin"] == {
        "airport": "BOM", "landing_inr": 31356.0, "parking_inr": 0.0, "total_inr": 31356.0, "total_usd": 368.89,
    }
    assert content["destination"] == {
        "airport": "DEL", "landing_inr": 27066.0, "parking_inr": 0.0, "total_inr": 27066.0, "total_usd": 318.42,
    }
    assert content["per_flight_inr"] == 27066.0
    assert content["weekly_change_if_one_weekly_flight_added_inr"] == 27066.0
    assert content["passenger_charges"]["per_passenger_inr"] == 231.0
    assert content["sources"] and content["snapshot_status"] == "FALLBACK"
    assert "curated" in content["snapshot_note"]


async def test_without_a_route_every_twin_route_gets_an_item(db_session, monkeypatch):
    await _prepare(db_session, monkeypatch)

    items = await provider(db_session, _request(None, "NETWORK"))

    assert [i.id for i in items] == ["airport:BLR-HYD", "airport:BOM-BLR", "airport:BOM-DEL", "airport:DEL-BOM", "airport:MAA-CCU"]
    assert len({i.id for i in items}) == len(items)


async def test_a_route_that_is_not_in_the_twin_still_reports_its_airports(db_session, monkeypatch):
    await _prepare(db_session, monkeypatch, seed=False)

    [item] = await provider(db_session, _request("BOM-DEL"))

    assert item.content["origin"]["airport"] == "BOM" and item.content["destination"]["landing_inr"] == 27066.0


async def test_nothing_is_returned_without_stored_charges(db_session, monkeypatch):
    monkeypatch.setattr(airport_charges_evidence, "_today", lambda: DAY)
    assert await provider(db_session, _request("BOM-DEL")) == []


async def test_a_route_with_no_published_charges_at_either_end_is_skipped(db_session, monkeypatch):
    await _prepare(db_session, monkeypatch, seed=False)
    assert await provider(db_session, _request("XXX-YYY")) == []


async def test_a_route_with_one_known_end_keeps_it_and_says_what_is_missing(db_session, monkeypatch):
    await _prepare(db_session, monkeypatch, seed=False)

    [item] = await provider(db_session, _request("BOM-XXX"))

    assert item.content["origin"]["airport"] == "BOM" and item.content["destination"] is None
    assert item.content["per_flight_inr"] is None
    assert any("XXX" in note for note in item.content["notes"])

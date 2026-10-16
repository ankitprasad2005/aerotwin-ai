import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from sqlalchemy import select

from app.datasets import airworthiness, common
from app.datasets.airworthiness import (
    aircraft_types_for, fetch_airworthiness_directives, parse_directives, search_url,
)
from app.datasets.common import DatasetError
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, AirworthinessDirective

FIXTURES = Path(__file__).parent / "fixtures" / "datasets"
A320 = (FIXTURES / "federal_register_ad_a320.json").read_bytes()
A321 = (FIXTURES / "federal_register_ad_a321.json").read_bytes()
B737 = (FIXTURES / "federal_register_ad_b737.json").read_bytes()
TODAY = date(2026, 10, 16)  # the day the fixtures were captured
AIRBUS = "Airworthiness Directives; Airbus SAS Airplanes"
BOEING = "Airworthiness Directives; The Boeing Company Airplanes"


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


@pytest.mark.parametrize(
    "title,abstract,expected",
    [
        (AIRBUS, "for certain Airbus SAS Model A320-214, -216 airplanes", ["A320"]),
        (AIRBUS, "for certain Airbus SAS Model A321-251NX airplanes", ["A321"]),
        (AIRBUS, "Model A319-111; Model A320 series airplanes; and Model A321-211", ["A320", "A321"]),
        (AIRBUS, "Model A318 and A319 series airplanes", []),  # A320-family but not a twin type
        (AIRBUS, "all Airbus SAS Model A330-200 airplanes", []),
        (AIRBUS, None, []),
        (BOEING, "certain The Boeing Company Model 737-8, 737-9, and 737-8200 airplanes", ["B737"]),
        (BOEING, "all The Boeing Company Model 737-, -200, -300 series airplanes", ["B737"]),
        (BOEING, "certain The Boeing Company Model 777-300ER airplanes", []),
        (BOEING, "Model 747-400 airplanes; the 737 MAX is not affected", ["B737"]),
        (BOEING, "Model 1737 airplanes", []),
        ("Requirements for Interference-Tolerant Radio Altimeter Systems", "Boeing 737 radio altimeters", []),
        ("Special Conditions: Airbus Models A321 neo ACF", "Airbus A321neo", []),
        ("Airworthiness Directives; McDonnell Douglas Airplanes", "Model A320 737", []),
        ("Airworthiness Directives; Airbus SAS Airplanes", "Boeing Model 737-800 and Airbus Model A320-214", ["A320"]),
    ],
)
def test_aircraft_types_for(title, abstract, expected):
    assert aircraft_types_for(title, abstract) == expected


def test_search_url_has_the_documented_filters():
    url = search_url("Airbus A320", date(2025, 10, 16))
    query = parse_qs(urlparse(url).query)
    assert url.startswith("https://www.federalregister.gov/api/v1/documents.json?")
    assert query["conditions[agencies][]"] == ["federal-aviation-administration"]
    assert query["conditions[type][]"] == ["RULE"]
    assert query["conditions[term]"] == ["Airbus A320"]
    assert query["conditions[publication_date][gte]"] == ["2025-10-16"]
    assert query["order"] == ["newest"] and query["per_page"] == ["100"]
    assert "page" not in query and parse_qs(urlparse(search_url("x", date(2025, 1, 1), page=2)).query)["page"] == ["2"]


def test_parse_directives_on_the_real_fixtures():
    rows = {r["document_number"]: r for r in parse_directives(A320, TODAY) + parse_directives(A321, TODAY) + parse_directives(B737, TODAY)}
    assert "2026-02110" not in rows  # a CVR rule, not an AD
    assert "2025-22163" not in rows  # special conditions
    assert "2026-15585" not in rows  # radio altimeter rule
    assert len(rows) == 33
    assert rows["2026-13062"]["aircraft_types"] == ["A321"]
    assert rows["2026-10490"]["aircraft_types"] == ["A320"]
    assert rows["2026-18052"]["aircraft_types"] == ["A320", "A321"]
    assert rows["2026-19082"] == {
        "document_number": "2026-19082", "title": BOEING, "publication_date": date(2026, 9, 17),
        "html_url": rows["2026-19082"]["html_url"], "abstract": rows["2026-19082"]["abstract"], "aircraft_types": ["B737"],
    }
    assert rows["2026-19082"]["html_url"].startswith("https://www.federalregister.gov/documents/2026/09/17/2026-19082/")
    assert all(r["aircraft_types"] for r in rows.values())


def test_parse_directives_keeps_only_the_last_365_days():
    payload = json.dumps({"results": [
        {"document_number": "n1", "title": AIRBUS, "publication_date": "2025-10-16", "html_url": "u1", "abstract": "A320"},
        {"document_number": "old", "title": AIRBUS, "publication_date": "2025-10-15", "html_url": "u2", "abstract": "A320"},
        {"document_number": "future", "title": AIRBUS, "publication_date": "2026-10-17", "html_url": "u3", "abstract": "A320"},
    ]}).encode()
    assert [r["document_number"] for r in parse_directives(payload, TODAY)] == ["n1", "future"]


def test_parse_directives_skips_unusable_entries():
    good = {"document_number": "ok", "title": AIRBUS, "publication_date": "2026-01-01", "html_url": "u", "abstract": "A320"}
    payload = json.dumps({"results": [
        "junk", {**good, "document_number": ""}, {**good, "document_number": "bad-date", "publication_date": "soon"},
        {**good, "document_number": "no-url", "html_url": None}, {**good, "document_number": "no-title", "title": None},
        {**good, "document_number": "no-abstract", "abstract": None}, good,
    ]}).encode()
    # An AD without an abstract names no twin type, so it is skipped too.
    assert [r["document_number"] for r in parse_directives(payload, TODAY)] == ["ok"]


@pytest.mark.parametrize("content", [b"not json", b"[]", b'{"results": "x"}', b'{}'])
def test_parse_directives_rejects_malformed_responses(content):
    with pytest.raises(DatasetError):
        parse_directives(content, TODAY)


def _mock_fr(a320=A320, a321=A321, b737=B737):
    bodies = {"Airbus A320": a320, "Airbus A321": a321, "Boeing 737": b737}

    def answer(request):
        term = request.url.params["conditions[term]"]
        return bodies[term] if isinstance(bodies[term], httpx.Response) else httpx.Response(200, content=bodies[term])

    return respx.get(url__startswith=airworthiness.API_URL).mock(side_effect=answer)


@respx.mock
async def test_fetch_stores_the_merged_deduplicated_directives(db_session, tmp_path):
    route = _mock_fr()

    snapshot = await fetch_airworthiness_directives(db_session, base_dir=tmp_path, today=TODAY)

    assert route.call_count == 3
    assert snapshot.source == "faa_airworthiness_directives" and snapshot.status == SNAPSHOT_SUCCESS
    rows = (await db_session.execute(select(AirworthinessDirective))).scalars().all()
    assert snapshot.row_count == len(rows) == 33  # the Airbus ADs appear in both Airbus queries but are stored once
    assert snapshot.details["by_type"] == {"A320": 22, "A321": 22, "B737": 10}
    assert snapshot.checksum and len(list(tmp_path.rglob("*.json"))) == 3
    assert all(r.snapshot_id == snapshot.id for r in rows)


@respx.mock
async def test_refetch_updates_rows_in_place(db_session, tmp_path):
    _mock_fr()
    await fetch_airworthiness_directives(db_session, base_dir=tmp_path, today=TODAY)
    row = (await db_session.execute(select(AirworthinessDirective).where(AirworthinessDirective.document_number == "2026-19082"))).scalar_one()
    row.title = "stale"
    await db_session.flush()

    second = await fetch_airworthiness_directives(db_session, base_dir=tmp_path, today=TODAY)

    assert second.status == SNAPSHOT_SUCCESS
    rows = (await db_session.execute(select(AirworthinessDirective))).scalars().all()
    assert len(rows) == 33
    await db_session.refresh(row)
    assert row.title == BOEING and row.snapshot_id == second.id


@respx.mock
async def test_fetch_follows_pagination(db_session, tmp_path):
    page1 = json.dumps({"total_pages": 2, "results": [
        {"document_number": "p1", "title": AIRBUS, "publication_date": "2026-05-01", "html_url": "u", "abstract": "A320"}]}).encode()
    page2 = json.dumps({"total_pages": 2, "results": [
        {"document_number": "p2", "title": AIRBUS, "publication_date": "2026-05-02", "html_url": "u", "abstract": "A320"}]}).encode()
    empty = json.dumps({"total_pages": 1, "results": []}).encode()

    def answer(request):
        if request.url.params["conditions[term]"] != "Airbus A320":
            return httpx.Response(200, content=empty)
        return httpx.Response(200, content=page2 if request.url.params.get("page") == "2" else page1)

    respx.get(url__startswith=airworthiness.API_URL).mock(side_effect=answer)

    snapshot = await fetch_airworthiness_directives(db_session, base_dir=tmp_path, today=TODAY)

    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.row_count == 2


@respx.mock
async def test_fetch_failure_is_a_failed_snapshot_without_invented_rows(db_session, tmp_path):
    _mock_fr(b737=httpx.Response(500))

    snapshot = await fetch_airworthiness_directives(db_session, base_dir=tmp_path, today=TODAY)

    assert snapshot.status == SNAPSHOT_FAILED and snapshot.row_count == 0 and "500" in snapshot.error
    assert (await db_session.execute(select(AirworthinessDirective))).scalars().all() == []


@respx.mock
async def test_malformed_or_empty_responses_fail_the_snapshot(db_session, tmp_path):
    _mock_fr(a320=b"<html>", a321=A321, b737=B737)
    assert (await fetch_airworthiness_directives(db_session, base_dir=tmp_path, today=TODAY)).status == SNAPSHOT_FAILED

    empty = json.dumps({"results": []}).encode()
    _mock_fr(a320=empty, a321=empty, b737=empty)
    failed = await fetch_airworthiness_directives(db_session, base_dir=tmp_path, today=TODAY)
    assert failed.status == SNAPSHOT_FAILED and "no airworthiness directives" in failed.error

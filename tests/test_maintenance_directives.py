from datetime import date, timedelta

from app.seed.seed import run_seed
from app.tools.digital_twin_tools import query_maintenance_status
from tests.ad_taf_data import add_directives


async def _by_tail(db):
    return {a["tail_number"]: a for a in (await query_maintenance_status(db))["maintenance"]}


async def test_without_directives_every_aircraft_reports_zero(db_session):
    await run_seed(db_session)

    for aircraft in (await _by_tail(db_session)).values():
        assert aircraft["recent_airworthiness_directives"] == {"count_last_365_days": 0, "newest": []}


async def test_each_aircraft_gets_the_directives_of_its_own_type(db_session):
    await run_seed(db_session)
    await add_directives(
        db_session,
        ("d1", 400, ["A320"]),  # older than 365 days: not counted
        ("d2", 90, ["A320"]),
        ("d3", 60, ["A320", "A321"]),
        ("d4", 30, ["A320"]),
        ("d5", 7, ["A320", "A321"]),
        ("d6", 20, ["B737"]),
    )

    tails = await _by_tail(db_session)

    # VT-AER1 and VT-AER2 are A320, VT-AER4 is A321, VT-AER3 is a B737.
    a320 = tails["VT-AER1"]["recent_airworthiness_directives"]
    assert a320["count_last_365_days"] == 4 and tails["VT-AER2"]["recent_airworthiness_directives"] == a320
    assert [d["document_number"] for d in a320["newest"]] == ["d5", "d4", "d3"]  # only the 3 newest
    assert a320["newest"][0] == {
        "document_number": "d5",
        "title": "Airworthiness Directives; Airbus SAS Airplanes",
        "publication_date": (date.today() - timedelta(days=7)).isoformat(),
        "summary": "The FAA is adopting a new AD for d5.",
    }
    a321 = tails["VT-AER4"]["recent_airworthiness_directives"]
    assert a321["count_last_365_days"] == 2 and [d["document_number"] for d in a321["newest"]] == ["d5", "d3"]
    b737 = tails["VT-AER3"]["recent_airworthiness_directives"]
    assert b737["count_last_365_days"] == 1 and [d["document_number"] for d in b737["newest"]] == ["d6"]


async def test_long_abstracts_are_shortened_and_a_missing_one_is_null(db_session):
    await run_seed(db_session)
    await add_directives(
        db_session,
        {"document_number": "long", "publication_date": date.today() - timedelta(days=2), "aircraft_types": ["B737"],
         "abstract": "x" * 600},
        {"document_number": "none", "publication_date": date.today() - timedelta(days=3), "aircraft_types": ["B737"],
         "abstract": None},
    )

    newest = (await _by_tail(db_session))["VT-AER3"]["recent_airworthiness_directives"]["newest"]

    assert len(newest[0]["summary"]) == 300 and newest[0]["summary"].endswith("...")
    assert newest[1]["summary"] is None


async def test_directives_never_change_the_airworthiness_classification(db_session):
    await run_seed(db_session)
    before = {t: a["airworthiness"] for t, a in (await _by_tail(db_session)).items()}
    await add_directives(db_session, *[(f"d{i}", i + 1, ["A320", "A321", "B737"]) for i in range(10)])

    after = {t: a["airworthiness"] for t, a in (await _by_tail(db_session)).items()}

    assert after == before

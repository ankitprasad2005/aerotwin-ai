from datetime import date

import pytest
from sqlalchemy import select

from app.datasets import airport_charges
from app.datasets.common import DatasetError
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_FALLBACK, AirportCharge

HEADER = (
    "airport,charge_type,basis,stand_type,aircraft_class,applies_to,slab_from_tonnes,slab_to_tonnes,base_inr,rate_inr,"
    "currency,hour_from,hour_to,rate_multiplier,free_hours,standard_added_hours,mt_rounding,hour_rounding,"
    "effective_from,effective_to,source_url,source_title,page,notes\n"
)
GOOD_ROW = "BOM,landing,per_tonne,all,all,domestic,0,,,402,INR,0,,1,,,up,,2025-05-16,2029-03-31,https://x.test/a.pdf,Order,501,\n"


def _csv(tmp_path, *rows: str):
    path = tmp_path / "charges.csv"
    path.write_text(HEADER + "".join(rows), encoding="utf-8")
    return path


def test_the_curated_csv_covers_the_six_twin_airports_and_cites_every_row():
    rows = airport_charges.load_curated()
    assert {r["airport"] for r in rows} == {"BOM", "DEL", "BLR", "HYD", "MAA", "CCU"}
    assert {r["charge_type"] for r in rows} == {"landing", "landing_minimum", "parking", "udf_embarking", "udf_disembarking"}
    for r in rows:
        assert r["source_url"].startswith("https://www.aera.gov.in/uploads/airports/")
        assert r["source_title"].startswith("AERA Order No.")
        assert r["page"] and r["effective_from"] and r["rate_inr"] > 0
        assert r["applies_to"] == "domestic" and r["currency"] == "INR"


def test_the_curated_csv_has_no_duplicate_keys():
    keys = [
        (r["airport"], r["charge_type"], r["applies_to"], r["stand_type"], r["aircraft_class"], r["slab_from_tonnes"],
         r["hour_from"], r["effective_from"])
        for r in airport_charges.load_curated()
    ]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize(
    "airport, charge_type, rate, effective_from, page",
    [
        # figures read from the AERA rate cards (see source_url/page in the CSV)
        ("DEL", "landing", 347.0, date(2025, 4, 16), "419"),   # Order 20/2024-25, narrow body, Rs per MT
        ("BOM", "landing", 402.0, date(2025, 5, 16), "501"),   # Order 01/2025-26
        ("BLR", "landing", 442.0, date(2026, 9, 1), "618"),    # Order 14/2026-27
        ("HYD", "landing", 435.0, date(2026, 9, 1), "540"),    # Order 15/2026-27
        ("DEL", "udf_embarking", 129.0, date(2025, 4, 16), "421"),
        ("BOM", "udf_disembarking", 75.0, date(2025, 5, 16), "502"),
        ("BLR", "udf_embarking", 300.0, date(2026, 9, 1), "619"),
        ("HYD", "udf_embarking", 515.0, date(2026, 9, 1), "541"),
        ("MAA", "udf_embarking", 410.0, date(2026, 1, 1), "208"),
        ("CCU", "udf_embarking", 547.0, date(2026, 1, 1), "205"),
    ],
)
def test_verified_figures_are_in_the_csv(airport, charge_type, rate, effective_from, page):
    matches = [
        r for r in airport_charges.load_curated()
        if r["airport"] == airport and r["charge_type"] == charge_type and r["effective_from"] == effective_from
        and r["aircraft_class"] in ("all", "narrow_body") and r["slab_from_tonnes"] == 0 and r["hour_from"] == 0
    ]
    assert [(m["rate_inr"], m["page"]) for m in matches][:1] == [(rate, page)]


def test_slab_and_tier_rows_keep_the_published_structure():
    rows = airport_charges.load_curated()
    maa = sorted(
        (r["slab_from_tonnes"], r["slab_to_tonnes"], r["base_inr"], r["rate_inr"])
        for r in rows if r["airport"] == "MAA" and r["charge_type"] == "landing"
    )
    assert maa == [(0, 25, None, 70), (25, 50, 1750, 82), (50, 100, 3800, 93), (100, 200, 8450, 105), (200, None, 18950, 128)]
    del_parking = sorted(
        (r["hour_from"], r["hour_to"], r["rate_multiplier"])
        for r in rows if r["airport"] == "DEL" and r["charge_type"] == "parking" and r["stand_type"] == "contact"
    )
    assert del_parking == [(0, 4, 1), (4, 12, 2), (12, 24, 4), (24, None, 5)]


def test_load_curated_rejects_a_row_without_a_source(tmp_path):
    path = _csv(tmp_path, GOOD_ROW.replace("https://x.test/a.pdf", ""))
    with pytest.raises(DatasetError, match="source_url"):
        airport_charges.load_curated(path)


def test_load_curated_rejects_a_row_without_a_rate(tmp_path):
    path = _csv(tmp_path, GOOD_ROW.replace(",402,", ",,"))
    with pytest.raises(DatasetError, match="rate_inr"):
        airport_charges.load_curated(path)


def test_load_curated_rejects_a_malformed_number_or_date(tmp_path):
    with pytest.raises(DatasetError, match="rate_inr is not a number"):
        airport_charges.load_curated(_csv(tmp_path, GOOD_ROW.replace(",402,", ",4o2,")))
    with pytest.raises(DatasetError, match="effective_from is not an ISO date"):
        airport_charges.load_curated(_csv(tmp_path, GOOD_ROW.replace("2025-05-16", "16/05/2025")))
    with pytest.raises(DatasetError, match="effective_to is not an ISO date"):
        airport_charges.load_curated(_csv(tmp_path, GOOD_ROW.replace("2029-03-31", "March 2029")))


def test_load_curated_applies_defaults_and_upper_cases_the_airport(tmp_path):
    [row] = airport_charges.load_curated(_csv(tmp_path, GOOD_ROW.replace("BOM,", "bom,", 1).replace(",all,all,domestic,0,,,", ",,,,,,,")))
    assert row["airport"] == "BOM" and row["stand_type"] == "all" and row["aircraft_class"] == "all"
    assert row["applies_to"] == "domestic" and row["slab_from_tonnes"] == 0.0 and row["hour_from"] == 0.0
    assert row["rate_multiplier"] == 1.0 and row["slab_to_tonnes"] is None and row["page"] == "501" and row["notes"] is None


def test_load_curated_rejects_an_empty_file(tmp_path):
    with pytest.raises(DatasetError, match="no rows"):
        airport_charges.load_curated(_csv(tmp_path))


def test_load_curated_missing_file(tmp_path):
    with pytest.raises(DatasetError, match="not found"):
        airport_charges.load_curated(tmp_path / "nope.csv")


async def test_fetch_loads_the_csv_and_marks_the_snapshot_as_curated(db_session):
    snapshot = await airport_charges.fetch_airport_charges(db_session)

    assert snapshot.source == "airport_charges"
    assert snapshot.status == SNAPSHOT_FALLBACK  # curated, not downloaded
    assert "curated" in snapshot.error and "AERA" in snapshot.error
    expected = len(airport_charges.load_curated())
    assert snapshot.row_count == expected
    stored = (await db_session.execute(select(AirportCharge))).scalars().all()
    assert len(stored) == expected
    assert all(r.snapshot_id == snapshot.id for r in stored)
    assert snapshot.details["airports"] == ["BLR", "BOM", "CCU", "DEL", "HYD", "MAA"]


async def test_fetch_replaces_rows_so_a_second_run_does_not_duplicate(db_session):
    await airport_charges.fetch_airport_charges(db_session)
    await airport_charges.fetch_airport_charges(db_session)
    count = len((await db_session.execute(select(AirportCharge))).scalars().all())
    assert count == len(airport_charges.load_curated())


async def test_fetch_failure_is_recorded_and_keeps_old_rows(db_session, tmp_path):
    await airport_charges.fetch_airport_charges(db_session)
    snapshot = await airport_charges.fetch_airport_charges(db_session, csv_path=tmp_path / "missing.csv")
    assert snapshot.status == SNAPSHOT_FAILED
    assert len((await db_session.execute(select(AirportCharge))).scalars().all()) == len(airport_charges.load_curated())


async def test_charge_rows_filters_by_airport(db_session):
    await airport_charges.fetch_airport_charges(db_session)
    rows = await airport_charges.charge_rows(db_session, "bom")
    assert rows and {r.airport for r in rows} == {"BOM"}
    assert len(await airport_charges.charge_rows(db_session)) > len(rows)

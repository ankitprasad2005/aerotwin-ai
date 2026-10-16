from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from app.datasets import aai_traffic, common
from app.datasets.aai_traffic import (
    AAI_IATA, FREIGHT, INDEX_URL, MOVEMENTS, PASSENGERS, check_month, combine, discover_reports, extract_pages,
    fetch_aai_traffic, latest_complete_periods, normalize_name, parse_annex, parse_row,
)
from app.datasets.common import DatasetError
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, AirportTrafficMonthly, IndiaAirport
from tests.aai_data import AAI_FIXTURES, annex_url, index_html, make_pages_pdf, mock_aai, pages_for, real_pages


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


@pytest.fixture
def datasets_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "get_settings", lambda: type("S", (), {"datasets_dir": str(tmp_path)})())
    return tmp_path


def _parsed():
    return {a: parse_annex(real_pages(a)) for a in (MOVEMENTS, PASSENGERS, FREIGHT)}


def test_parse_row_reads_a_movements_row():
    line = "4 चेन्नई CHENNAI 3302 3593 -8.1% 16228 17671 -8.2%"
    assert parse_row(line) == ("CHENNAI", 3302.0, -8.1)


def test_parse_row_keeps_decimals_and_a_missing_percentage():
    assert parse_row("3भवु ने(cid:16)वर BHUBANESWAR 0.0 5.6 - 0.0 49.0 -") == ("BHUBANESWAR", 0.0, None)


def test_parse_row_ignores_ascii_debris_left_by_garbled_hindi():
    assert parse_row("12C COOCHBEHER 0 0 - 0 0 -")[0] == "COOCHBEHER"
    assert parse_row("27 (F) ITANAGAR (HOLONGI) 5 6 -16.7% 7 8 -")[0] == "ITANAGAR (HOLONGI)"
    assert parse_row("24+U SHRAVASTI 5 6 -16.7% 7 8 -")[0] == "SHRAVASTI"
    assert parse_row("49 (IJ) MOHANBARI (DIBRUGARH) 5 6 -16.7% 7 8 -")[0] == "MOHANBARI (DIBRUGARH)"
    assert parse_row("24+U SHRAVASTI 0.0 0.0 - 0.0 0.0 -")[0] == "SHRAVASTI"
    assert parse_row("5 K) NASIK (HAL OZAR) 5 6 -16.7% 7 8 -")[0] == "NASIK (HAL OZAR)"


def test_parse_row_survives_garbled_hindi_and_parenthesised_names():
    assert parse_row("51वशाखाप(cid:23)नम VISAKHAPATNAM (GVIAL) 341.6 365.1 -6.4% 1905.4 2249.9 -15.3%")[0] == "VISAKHAPATNAM (GVIAL)"
    assert parse_row("31जGम ूJAMMU 81.6 98.4 -17.0% 438.9 188.6 -") == ("JAMMU", 81.6, -17.0)
    assert parse_row("1 आइजोल (लेंगपुई) AIZAWL(LENGPUI) 286 281 1.8% 1440 1621 -11.2%")[0] == "AIZAWL (LENGPUI)"


@pytest.mark.parametrize(
    "line",
    [
        "योग Total 7932 8781 -9.7% 37688 43754 -13.9%",
        "कु ल योग Grand Total 39638 40944 -3.2% 185834 201973 -8.0%",
        "2026 2025 प(cid:6)रवतन(cid:9) Change 2026-2027 2025-2026",
        "Note:This report is compiled on the basis of data provided by the respective airport and is subject to revision.",
        "1 अमृतसर AMRITSAR 401 472 x 1891 2437 -22.4%",
        "1 123 456 7% 1891 2437 -22.4% 5 5",
        "",
    ],
)
def test_parse_row_ignores_headings_totals_and_malformed_rows(line):
    assert parse_row(line) is None


def test_normalize_name_folds_the_spelling_differences_between_tables():
    assert normalize_name("DELHI (DIAL)") == "DELHI"
    assert normalize_name("GOA") == "GOA (DABOLIM)"
    assert normalize_name("&SINDHUDURG") == "SINDHUDURG"
    assert normalize_name("NAVI MUMBAI(NMIAL)") == "NAVI MUMBAI (NMIAL)"


def test_parse_annex_splits_international_domestic_and_total_parts():
    movements = parse_annex(real_pages(MOVEMENTS))

    assert {scope: len(rows) for scope, rows in movements.items()} == {"A": 51, "B": 148, "C": 148}
    assert movements["C"]["CHENNAI"][0] == 3302.0 + 7952.0
    assert movements["A"]["CHENNAI"] == (3302.0, -8.1)
    assert movements["B"]["CHENNAI"] == (7952.0, -17.4)


def test_the_real_annexures_sum_to_the_published_grand_totals():
    rows = combine("2026-08", _parsed())

    assert len(rows) == 148
    assert sum(r["aircraft_movements"] for r in rows) == 223906  # "Grand Total" of annexure II C
    assert sum(r["passengers"] for r in rows) == 31013368  # annexure III C
    assert round(sum(r["freight_tonnes"] for r in rows), 0) == 369878  # annexure IV C: 369878.3 t
    assert sum(r["movements_domestic"] + r["movements_international"] for r in rows if r["movements_international"] is not None) > 0


def test_combine_builds_the_delhi_row_from_all_three_annexures():
    delhi = next(r for r in combine("2026-08", _parsed()) if r["airport_name"] == "DELHI")

    assert delhi == {
        "airport_name": "DELHI", "iata_code": "DEL", "period": "2026-08",
        "aircraft_movements": 40160, "passengers": 6083616, "freight_tonnes": 106425.6,
        "movements_domestic": 30309, "movements_international": 9851,
        "passengers_domestic": 4389269, "passengers_international": 1694347,
        "freight_domestic_tonnes": 34660.3, "freight_international_tonnes": 71765.3,
        "movements_yoy_pct": 11.4, "passengers_yoy_pct": 2.7, "freight_yoy_pct": 10.6,
    }


def test_combine_leaves_a_split_empty_when_the_airport_is_not_in_that_part():
    rows = {r["airport_name"]: r for r in combine("2026-08", _parsed())}

    assert rows["JODHPUR"]["movements_international"] is None


def test_every_airport_name_is_mapped_or_deliberately_unmapped():
    names = {r["airport_name"] for r in combine("2026-08", _parsed())}
    assert names <= set(AAI_IATA)
    unmapped = {n for n in names if AAI_IATA[n] is None}
    assert {"JUHU", "SAFDARJUNG", "BENGALURU (HAL)"} <= unmapped
    assert len(names) - len(unmapped) > 130


def test_check_month_accepts_the_matching_month_and_the_scrambled_annexure_four():
    check_month(real_pages(MOVEMENTS), "2026-08")
    check_month(real_pages(FREIGHT), "2026-08")  # its heading names no month in English


def test_check_month_rejects_a_different_month():
    with pytest.raises(DatasetError, match="does not match"):
        check_month(real_pages(MOVEMENTS), "2026-07")


def test_check_month_rejects_a_different_year():
    with pytest.raises(DatasetError, match="does not match"):
        check_month(["ANNEXURE August 2024-2025"], "2026-08")


def test_extract_pages_reads_a_real_aai_pdf():
    pages = extract_pages((AAI_FIXTURES / "Aug2k26Annex_4.pdf").read_bytes())

    assert len(pages) == 7
    parsed = parse_annex(pages)
    assert parsed["C"]["MUMBAI (MIAL)"] == (81532.3, 7.6)
    assert parsed["C"]["KOCHI"][0] > 0  # one of the garbled-Hindi rows
    assert pages == real_pages(FREIGHT)


def test_discover_reports_lists_every_month_and_annexure_variant():
    reports = discover_reports(index_html().decode())

    assert set(reports) == {"2026-08", "2026-07", "2026-06", "2026-04"}
    assert reports["2026-08"][4].endswith("/Aug2k26Annex_4.pdf")
    assert reports["2026-04"][5].endswith("/April2k26Anex5.pdf")  # AAI's own typo
    assert reports["2026-07"][2] == annex_url("Jul2k26", 2)
    assert latest_complete_periods(reports) == ["2026-08", "2026-07"]
    assert latest_complete_periods(reports, 1) == ["2026-08"]


def test_discover_reports_ignores_unrelated_and_unknown_links():
    html = (
        '<a href="/sites/default/files/traffic-news/Foo2k26Annex2.pdf">x</a>'
        '<a href="/sites/default/files/traffic-news/TRAug2k26.pdf">summary</a>'
        '<a href="/sites/default/files/other/Aug2k26Annex2.pdf">elsewhere</a>'
        '<a href="/sites/default/files/traffic-news/Jan2k26Annex2_0.pdf">ok</a>'
    )
    assert discover_reports(html) == {"2026-01": {2: "https://www.aai.aero/sites/default/files/traffic-news/Jan2k26Annex2_0.pdf"}}
    assert latest_complete_periods({"2026-01": {2: "u", 3: "u"}}) == []


@respx.mock
async def test_fetch_stores_the_latest_two_months(db_session, datasets_tmp):
    mock_aai(respx)
    db_session.add(IndiaAirport(ident="VIDP", icao_code="VIDP", iata_code="DEL", name="Indira Gandhi", airport_type="large_airport"))
    await db_session.flush()

    snapshot = await fetch_aai_traffic(db_session)

    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.error is None
    assert snapshot.row_count == 296 and snapshot.source_url == INDEX_URL
    assert snapshot.details == {"periods": ["2026-07", "2026-08"], "latest_period": "2026-08", "airports": 148}
    assert snapshot.checksum and Path(snapshot.local_path).exists()
    rows = (await db_session.execute(select(AirportTrafficMonthly).where(AirportTrafficMonthly.iata_code == "DEL"))).scalars().all()
    assert sorted(r.period for r in rows) == ["2026-07", "2026-08"]
    delhi = next(r for r in rows if r.period == "2026-08")
    assert delhi.passengers == 6083616 and delhi.icao_code == "VIDP" and delhi.snapshot_id == snapshot.id
    # Airports without an IATA code are kept by name.
    juhu = (await db_session.execute(select(AirportTrafficMonthly).where(AirportTrafficMonthly.airport_name == "JUHU"))).scalars().first()
    assert juhu.iata_code is None and juhu.icao_code is None


@respx.mock
async def test_fetch_twice_updates_rows_in_place(db_session, datasets_tmp):
    mock_aai(respx)
    await fetch_aai_traffic(db_session)
    await fetch_aai_traffic(db_session)

    assert len((await db_session.execute(select(AirportTrafficMonthly))).scalars().all()) == 296


@respx.mock
async def test_fetch_fails_when_the_index_lists_no_complete_month(db_session, datasets_tmp):
    respx.get(INDEX_URL).mock(return_value=httpx.Response(200, content=b"<html>nothing here</html>"))

    snapshot = await fetch_aai_traffic(db_session)

    assert snapshot.status == SNAPSHOT_FAILED and "no month" in snapshot.error
    assert (await db_session.execute(select(AirportTrafficMonthly))).scalars().all() == []


@respx.mock
async def test_fetch_fails_when_aai_is_unreachable(db_session, datasets_tmp):
    respx.get(INDEX_URL).mock(return_value=httpx.Response(503))

    snapshot = await fetch_aai_traffic(db_session)

    assert snapshot.status == SNAPSHOT_FAILED and "failed" in snapshot.error and snapshot.row_count == 0


@respx.mock
async def test_fetch_fails_on_an_unreadable_pdf(db_session, datasets_tmp):
    mock_aai(respx)
    respx.get(annex_url("Aug2k26", 3)).mock(return_value=httpx.Response(200, content=b"%PDF-not really"))

    snapshot = await fetch_aai_traffic(db_session)

    assert snapshot.status == SNAPSHOT_FAILED and "unreadable" in snapshot.error
    assert (await db_session.execute(select(AirportTrafficMonthly))).scalars().all() == []


@respx.mock
async def test_fetch_fails_when_an_annexure_is_for_another_month(db_session, datasets_tmp):
    mock_aai(respx)
    respx.get(annex_url("Aug2k26", 2)).mock(
        return_value=httpx.Response(200, content=make_pages_pdf(pages_for(MOVEMENTS, "March")))
    )

    snapshot = await fetch_aai_traffic(db_session)

    assert snapshot.status == SNAPSHOT_FAILED and "does not match" in snapshot.error


@respx.mock
async def test_fetch_fails_when_an_annexure_has_no_airport_rows(db_session, datasets_tmp):
    mock_aai(respx)
    respx.get(annex_url("Aug2k26", 4)).mock(
        return_value=httpx.Response(200, content=make_pages_pdf(["ANNEXURE-IV C\nFreight August 2026\nlayout changed"]))
    )

    snapshot = await fetch_aai_traffic(db_session)

    assert snapshot.status == SNAPSHOT_FAILED and "no airport rows" in snapshot.error

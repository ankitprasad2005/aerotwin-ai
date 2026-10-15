import httpx
import pytest
import respx
from sqlalchemy import select

from app.datasets import common, dgca
from app.datasets.dgca import (
    PAGE_URL,
    discover_pdf,
    fetch_dgca,
    infer_period,
    load_fallback,
    parse_traffic_text,
)
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_FALLBACK, SNAPSHOT_SUCCESS, DgcaTraffic
from tests.datasets_pdf import make_pdf

PDF_URL = "https://www.dgca.gov.in/digigov-portal/jsp/dgca/reports/domestic_traffic_april_2026.pdf"
# Parser-test inputs only: made-up carriers and numbers, never stored in the shipped fallback CSV.
REPORT_LINES = [
    "Domestic Air Traffic Report April 2026",
    "Sl Airline Passengers Market Share Load Factor",
    "1 Synth Air 7,800,000 65.5 85.2",
    "2 Test Wings 3,100,000 25.9 88.0",
    "3 Tiny Jet 120,000 1.0",
    "Total 11,020,000 100.0 86.0",
]


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


# --- period / discovery -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Traffic Report April 2026", "2026-04"),
        ("domestic_traffic_apr-26.pdf", "2026-04"),
        ("Sept 2025", "2025-09"),
        ("DECEMBER_2024", "2024-12"),
        ("may 2026", "2026-05"),
        ("no date here", None),
        ("", None),
    ],
)
def test_infer_period(text, expected):
    assert infer_period(text) == expected


def test_discover_pdf_picks_the_latest_traffic_pdf():
    html = (
        '<a href="/files/domestic traffic march 2026.pdf">m</a>'
        '<a href="files/Domestic%20Traffic%20April%202026.pdf">a</a>'
        '<a href="/files/other_report_may_2026.pdf">not traffic</a>'
        '<a href="/files/traffic_no_month.pdf">no period</a>'
        '<a href="/page.html?x=traffic_june_2026">not a pdf</a>'
    )
    url, period = discover_pdf(html, "https://www.dgca.gov.in/digigov-portal/")
    assert period == "2026-04"
    assert url == "https://www.dgca.gov.in/digigov-portal/files/Domestic%20Traffic%20April%202026.pdf"


def test_discover_pdf_returns_none_without_candidates():
    assert discover_pdf("<html>nothing</html>") is None
    assert discover_pdf("") is None


# --- text parsing --------------------------------------------------------------------------------


def test_parse_traffic_text_extracts_rows():
    rows = parse_traffic_text("\n".join(REPORT_LINES))
    assert rows == [
        {"airline": "Synth Air", "passengers": 7_800_000, "market_share_pct": 65.5, "load_factor_pct": 85.2},
        {"airline": "Test Wings", "passengers": 3_100_000, "market_share_pct": 25.9, "load_factor_pct": 88.0},
        {"airline": "Tiny Jet", "passengers": 120_000, "market_share_pct": 1.0, "load_factor_pct": None},
    ]


def test_parse_traffic_text_edge_cases():
    text = "\n".join(
        [
            "",
            "12345",  # no name
            "A1 5",  # name too short / no letters pair
            "Alpha Air 5,000 10.5 80",
            "Alpha Air 9,999 99.0 99.0",  # duplicate: first wins
            "Beta Air 12.5",  # share only
            "Gamma Air",  # no numbers
            "Delta Air 150 200",  # nothing in range and passengers < 1000
            "Industry average 1,000 5.0",
            "Source: DGCA 2026",
        ]
    )
    rows = parse_traffic_text(text)
    assert [r["airline"] for r in rows] == ["Alpha Air", "Beta Air"]
    assert rows[0]["passengers"] == 5000
    assert rows[1] == {"airline": "Beta Air", "passengers": None, "market_share_pct": 12.5, "load_factor_pct": None}


def test_parse_traffic_text_empty():
    assert parse_traffic_text("") == []


# --- fallback CSV --------------------------------------------------------------------------------


def test_shipped_fallback_csv_is_header_only_or_fully_sourced():
    for row in load_fallback():
        assert row["source_url"].startswith("http") and row["is_fallback"] is True
        assert len(row["period"]) == 7


def test_load_fallback_parses_rows_and_skips_bad_ones(tmp_path):
    path = tmp_path / "fb.csv"
    path.write_text(
        "period,airline,passengers,market_share_pct,load_factor_pct,source_url\n"
        "2026-03,Alpha,1000,50.5,80.1,https://x/y.pdf\n"
        "2026-03,Alpha,2000,60.0,81.0,https://x/y.pdf\n"  # duplicate key, last wins
        "2026-03,Beta,,,,https://x/y.pdf\n"  # nulls
        "2026-03,NoUrl,1,1,1,\n"  # missing source_url
        ",NoPeriod,1,1,1,https://x\n"  # missing period
        "2026-03,,1,1,1,https://x\n"  # missing airline
        "2026-03,Bad,abc,xyz,,https://x\n",  # unparseable numbers become None
        encoding="utf-8",
    )
    rows = {r["airline"]: r for r in load_fallback(path)}
    assert set(rows) == {"Alpha", "Beta", "Bad"}
    assert rows["Alpha"]["passengers"] == 2000 and rows["Alpha"]["market_share_pct"] == 60.0
    assert rows["Beta"]["passengers"] is None and rows["Beta"]["load_factor_pct"] is None
    assert rows["Bad"]["passengers"] is None and rows["Bad"]["market_share_pct"] is None


def test_load_fallback_missing_or_empty_file(tmp_path):
    assert load_fallback(tmp_path / "missing.csv") == []
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    assert load_fallback(empty) == []


# --- fetch_dgca ----------------------------------------------------------------------------------

PAGE_HTML = f'<html><a href="{PDF_URL}">Domestic traffic April 2026</a></html>'


@respx.mock
async def test_fetch_dgca_parses_the_latest_pdf(db_session, tmp_path):
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=PAGE_HTML))
    respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=make_pdf(REPORT_LINES)))

    snap = await fetch_dgca(db_session, base_dir=tmp_path, fallback_path=tmp_path / "none.csv")

    assert snap.status == SNAPSHOT_SUCCESS and snap.row_count == 3 and snap.details == {"period": "2026-04"}
    rows = (await db_session.execute(select(DgcaTraffic).order_by(DgcaTraffic.airline))).scalars().all()
    assert [(r.period, r.airline, r.passengers, r.is_fallback, r.source_url) for r in rows][0] == (
        "2026-04", "Synth Air", 7_800_000, False, PDF_URL
    )


@respx.mock
async def test_fetch_dgca_falls_back_when_no_pdf_is_found(db_session, tmp_path):
    csv_path = tmp_path / "fb.csv"
    csv_path.write_text(
        "period,airline,passengers,market_share_pct,load_factor_pct,source_url\n2026-03,Alpha,1000,50.5,80.1,https://x/y.pdf\n",
        encoding="utf-8",
    )
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text="<html>no links</html>"))

    snap = await fetch_dgca(db_session, base_dir=tmp_path, fallback_path=csv_path)

    assert snap.status == SNAPSHOT_FALLBACK and snap.row_count == 1
    assert "no monthly domestic traffic PDF" in snap.error and snap.details == {"periods": ["2026-03"]}
    (row,) = (await db_session.execute(select(DgcaTraffic))).scalars().all()
    assert row.is_fallback is True and row.airline == "Alpha"


@respx.mock
async def test_fetch_dgca_falls_back_when_the_pdf_is_unreadable(db_session, tmp_path):
    csv_path = tmp_path / "fb.csv"
    csv_path.write_text(
        "period,airline,passengers,market_share_pct,load_factor_pct,source_url\n2026-03,Alpha,,,,https://x\n", encoding="utf-8"
    )
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=PAGE_HTML))
    respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=b"%PDF-1.4 garbage"))

    snap = await fetch_dgca(db_session, base_dir=tmp_path, fallback_path=csv_path)

    assert snap.status == SNAPSHOT_FALLBACK and "unreadable" in snap.error


@respx.mock
async def test_fetch_dgca_falls_back_when_the_pdf_has_no_airline_rows(db_session, tmp_path):
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=PAGE_HTML))
    respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=make_pdf(["Nothing useful here"])))
    csv_path = tmp_path / "fb.csv"
    csv_path.write_text(
        "period,airline,passengers,market_share_pct,load_factor_pct,source_url\n2026-03,Alpha,,,,https://x\n", encoding="utf-8"
    )

    snap = await fetch_dgca(db_session, base_dir=tmp_path, fallback_path=csv_path)

    assert snap.status == SNAPSHOT_FALLBACK and "no airline rows" in snap.error


@respx.mock
async def test_fetch_dgca_fails_when_live_and_fallback_both_unavailable(db_session, tmp_path):
    respx.get(PAGE_URL).mock(side_effect=httpx.ConnectTimeout("slow"))

    snap = await fetch_dgca(db_session, base_dir=tmp_path, fallback_path=tmp_path / "none.csv")

    assert snap.status == SNAPSHOT_FAILED and "fallback CSV has no rows" in snap.error
    assert (await db_session.execute(select(DgcaTraffic))).scalars().all() == []


@respx.mock
async def test_fetch_dgca_real_rows_replace_fallback_rows_for_the_same_period(db_session, tmp_path):
    csv_path = tmp_path / "fb.csv"
    csv_path.write_text(
        "period,airline,passengers,market_share_pct,load_factor_pct,source_url\n2026-04,Synth Air,1,1.0,1.0,https://x\n",
        encoding="utf-8",
    )
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text="nothing"))
    await fetch_dgca(db_session, base_dir=tmp_path, fallback_path=csv_path)

    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=PAGE_HTML))
    respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=make_pdf(REPORT_LINES)))
    await fetch_dgca(db_session, base_dir=tmp_path, fallback_path=csv_path)

    rows = (await db_session.execute(select(DgcaTraffic).where(DgcaTraffic.airline == "Synth Air"))).scalars().all()
    assert len(rows) == 1 and rows[0].is_fallback is False and rows[0].passengers == 7_800_000


def test_module_exposes_source_name():
    assert dgca.SOURCE == "dgca"

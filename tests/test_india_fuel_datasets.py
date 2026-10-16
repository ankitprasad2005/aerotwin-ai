from datetime import date
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from app.datasets import common, fbil, iocl_atf, ppac_crude
from app.datasets.common import DatasetError
from app.datasets.fbil import fetch_fbil, parse_fbil
from app.datasets.iocl_atf import fetch_iocl_atf, parse_iocl_atf
from app.datasets.ppac_crude import fetch_ppac_crude, financial_years, parse_ppac_icb
from app.models.external import (
    SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, AtfPriceIndia, FxReferenceIndia, IndianCrudeBasket,
)

FIXTURES = Path(__file__).parent / "fixtures" / "datasets"
IOCL_ATF = (FIXTURES / "iocl_atf_excerpt.html").read_bytes()
IOCL_CHALLENGE = (FIXTURES / "iocl_sucuri_challenge.html").read_bytes()
FBIL = (FIXTURES / "fbil_ref_rates.json").read_bytes()
ICB = {y: (FIXTURES / f"ppac_icb_{y}-{y + 1}.json").read_bytes() for y in (2024, 2025, 2026)}


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


@pytest.fixture
def datasets_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "get_settings", lambda: type("S", (), {"datasets_dir": str(tmp_path)})())
    return tmp_path


# --- IOCL ATF ---------------------------------------------------------------------------------

def test_parse_iocl_real_excerpt():
    rows = parse_iocl_atf(IOCL_ATF)
    assert len(rows) == 8
    by = {(r["city"], r["category"]): r for r in rows}
    assert by[("Delhi", "domestic")] == {
        "city": "Delhi", "price_month": date(2026, 4, 1), "category": "domestic", "inr_per_kl": 104927.0, "usd_per_kl": None,
    }
    assert by[("Kolkata", "domestic")]["inr_per_kl"] == 109450.0
    assert by[("Mumbai", "domestic")]["inr_per_kl"] == 98247.0
    assert by[("Chennai", "domestic")]["inr_per_kl"] == 109873.0
    assert by[("Delhi", "international")]["usd_per_kl"] == 1690.81
    assert by[("Delhi", "international")]["inr_per_kl"] is None
    assert by[("Chennai", "international")]["usd_per_kl"] == 1684.98


def test_parse_iocl_ignores_other_tables_and_bad_values():
    html = """
    <h2>Kerosene</h2><h3>Last updated on April 1, 2026</h3><table><tr><td>Delhi</td><td>10</td></tr></table>
    <h2>ATF Prices in Metros (Rupees/Kl) for Domestic Airlines</h2><h3>Last updated on May 1, 2026</h3>
    <table><tr><th>Metros</th><th>Prices</th></tr><tr><td>Delhi</td><td>1,00,000</td></tr>
    <tr><td>Pune</td><td>5</td></tr><tr><td>Mumbai</td><td>n/a</td></tr><tr><td>Chennai</td><td>0</td></tr></table>
    <h2>ATF Prices in Metros (Rupees/Kl) for Foreign Airlines</h2><h3>Last updated on someday</h3>
    <table><tr><td>Delhi</td><td>7</td></tr></table>
    <h2>ATF Prices in Metros (Euro/Kl)</h2><h3>Last updated on May 1, 2026</h3><table><tr><td>Delhi</td><td>7</td></tr></table>
    """
    rows = parse_iocl_atf(html)
    assert [(r["city"], r["inr_per_kl"], r["price_month"]) for r in rows] == [("Delhi", 100000.0, date(2026, 5, 1))]
    assert parse_iocl_atf(b"<html></html>") == []


@respx.mock
async def test_fetch_iocl_live_page_when_not_blocked(db_session, datasets_tmp):
    respx.get(iocl_atf.PAGE_URL).mock(return_value=httpx.Response(200, content=IOCL_ATF))
    snapshot = await fetch_iocl_atf(db_session)
    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.row_count == 8
    assert snapshot.details["via"] == "iocl" and snapshot.details["price_months"] == ["2026-04-01"]
    assert len((await db_session.execute(select(AtfPriceIndia))).scalars().all()) == 8
    assert Path(snapshot.local_path).read_bytes() == IOCL_ATF


@respx.mock
async def test_fetch_iocl_falls_back_to_the_archive_when_the_challenge_blocks(db_session, datasets_tmp):
    live = respx.get(iocl_atf.PAGE_URL).mock(return_value=httpx.Response(307, content=IOCL_CHALLENGE))
    respx.get(iocl_atf.WAYBACK_URL).mock(
        return_value=httpx.Response(200, content=IOCL_ATF, headers={"memento-datetime": "Fri, 12 Jun 2026 13:47:37 GMT"})
    )
    async with httpx.AsyncClient(follow_redirects=True) as client:
        snapshot = await fetch_iocl_atf(db_session, client=client)
    assert live.called
    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.row_count == 8
    assert snapshot.details["via"] == "wayback"
    assert snapshot.details["captured_at"] == "Fri, 12 Jun 2026 13:47:37 GMT"


@respx.mock
async def test_fetch_iocl_fallback_also_used_for_a_page_without_atf_table(db_session, datasets_tmp):
    respx.get(iocl_atf.PAGE_URL).mock(return_value=httpx.Response(200, content=b"<html>nothing</html>"))
    respx.get(iocl_atf.WAYBACK_URL).mock(return_value=httpx.Response(200, content=IOCL_ATF))
    snapshot = await fetch_iocl_atf(db_session)
    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.details["via"] == "wayback"
    assert snapshot.details["captured_at"] is None


@respx.mock
async def test_fetch_iocl_fails_when_challenge_and_archive_both_fail(db_session, datasets_tmp):
    respx.get(iocl_atf.PAGE_URL).mock(return_value=httpx.Response(307, content=IOCL_CHALLENGE))
    respx.get(iocl_atf.WAYBACK_URL).mock(return_value=httpx.Response(404))
    snapshot = await fetch_iocl_atf(db_session)
    assert snapshot.status == SNAPSHOT_FAILED
    assert "JavaScript challenge" in snapshot.error and "HTTP 404" in snapshot.error
    assert (await db_session.execute(select(AtfPriceIndia))).scalars().all() == []


@respx.mock
async def test_fetch_iocl_fails_when_even_the_archive_has_no_table(db_session, datasets_tmp):
    respx.get(iocl_atf.PAGE_URL).mock(return_value=httpx.Response(200, content=b"<html></html>"))
    respx.get(iocl_atf.WAYBACK_URL).mock(return_value=httpx.Response(200, content=b"<html></html>"))
    snapshot = await fetch_iocl_atf(db_session)
    assert snapshot.status == SNAPSHOT_FAILED and "no parseable ATF prices" in snapshot.error


@respx.mock
async def test_fetch_iocl_retries_server_errors_then_fails(db_session, datasets_tmp):
    route = respx.get(iocl_atf.PAGE_URL).mock(return_value=httpx.Response(503))
    snapshot = await fetch_iocl_atf(db_session)
    assert snapshot.status == SNAPSHOT_FAILED and "failed" in snapshot.error
    assert route.call_count == common.DEFAULT_RETRIES


@respx.mock
async def test_fetch_iocl_retries_transport_errors(db_session, datasets_tmp):
    respx.get(iocl_atf.PAGE_URL).mock(side_effect=[httpx.ConnectError("x"), httpx.Response(200, content=IOCL_ATF)])
    snapshot = await fetch_iocl_atf(db_session)
    assert snapshot.status == SNAPSHOT_SUCCESS


@respx.mock
async def test_fetch_iocl_refresh_updates_existing_rows(db_session, datasets_tmp):
    respx.get(iocl_atf.PAGE_URL).mock(return_value=httpx.Response(200, content=IOCL_ATF))
    await fetch_iocl_atf(db_session)
    await fetch_iocl_atf(db_session)
    assert len((await db_session.execute(select(AtfPriceIndia))).scalars().all()) == 8


# --- PPAC crude basket --------------------------------------------------------------------------

def test_parse_ppac_real_fixtures():
    fy26 = parse_ppac_icb(ICB[2026], 2026)
    assert fy26 == [
        (date(2026, 4, 1), 114.48), (date(2026, 5, 1), 106.23), (date(2026, 6, 1), 83.22), (date(2026, 7, 1), 82.04),
        (date(2026, 8, 1), 90.19), (date(2026, 9, 1), 116.09), (date(2026, 10, 1), 122.01),
    ]
    fy25 = parse_ppac_icb(ICB[2025], 2025)
    assert len(fy25) == 12 and fy25[0] == (date(2025, 4, 1), 67.72) and fy25[-1] == (date(2026, 3, 1), 113.49)
    assert parse_ppac_icb(ICB[2024], 2024)[3] == (date(2024, 7, 1), 84.15)


def test_parse_ppac_edge_cases():
    assert parse_ppac_icb(b'{"result":[],"token":"x"}', 2020) == []
    assert parse_ppac_icb(ICB[2026], 2030) == []  # no row for that year
    assert parse_ppac_icb(b'{"result":[{"title":"2020-21","april":5.0,"may":true,"june":"","july":-1}]}', 2020) == [
        (date(2020, 4, 1), 5.0)
    ]
    for junk in (b"", b"nope", b"[]", b'{"a":1}'):
        with pytest.raises(DatasetError, match="malformed"):
            parse_ppac_icb(junk, 2026)


def test_financial_years():
    assert financial_years(date(2026, 10, 16)) == [2023, 2024, 2025, 2026]
    assert financial_years(date(2026, 2, 1), 2) == [2024, 2025]


def _mock_ppac(status=200):
    def reply(request):
        body = request.content.decode()
        for year, content in ICB.items():
            if f"financialYear={year}-{year + 1}" in body:
                return httpx.Response(status, content=content)
        return httpx.Response(status, content=b'{"result":[]}')

    return respx.post(ppac_crude.AJAX_URL).mock(side_effect=reply)


@respx.mock
async def test_fetch_ppac_stores_the_monthly_series(db_session, datasets_tmp, monkeypatch):
    monkeypatch.setattr(ppac_crude, "financial_years", lambda today: [2024, 2025, 2026])
    route = _mock_ppac()
    snapshot = await fetch_ppac_crude(db_session)
    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.row_count == 12 + 12 + 7
    assert route.call_count == 3
    assert snapshot.details["last_month"] == "2026-10-01" and snapshot.details["latest_is_month_to_date"] is True
    rows = (await db_session.execute(select(IndianCrudeBasket).order_by(IndianCrudeBasket.price_month))).scalars().all()
    assert rows[-1].price_month == date(2026, 10, 1) and rows[-1].usd_per_bbl == 122.01
    assert "financialYear=2026-2027" in route.calls[-1].request.content.decode()


@respx.mock
async def test_fetch_ppac_fails_without_prices_or_on_errors(db_session, datasets_tmp, monkeypatch):
    monkeypatch.setattr(ppac_crude, "financial_years", lambda today: [2010])
    _mock_ppac()
    snapshot = await fetch_ppac_crude(db_session)
    assert snapshot.status == SNAPSHOT_FAILED and "no Indian basket prices" in snapshot.error


@respx.mock
async def test_fetch_ppac_retries_server_errors_but_not_client_errors(db_session, datasets_tmp):
    route = respx.post(ppac_crude.AJAX_URL).mock(return_value=httpx.Response(500))
    snapshot = await fetch_ppac_crude(db_session)
    assert snapshot.status == SNAPSHOT_FAILED and route.call_count == common.DEFAULT_RETRIES
    route.reset()
    route.mock(return_value=httpx.Response(403))
    snapshot = await fetch_ppac_crude(db_session)
    assert snapshot.status == SNAPSHOT_FAILED and route.call_count == 1


@respx.mock
async def test_fetch_ppac_supplied_client_is_left_open(db_session, datasets_tmp, monkeypatch):
    monkeypatch.setattr(ppac_crude, "financial_years", lambda today: [2026])
    _mock_ppac()
    async with httpx.AsyncClient() as client:
        snapshot = await fetch_ppac_crude(db_session, client=client)
        assert not client.is_closed
    assert snapshot.status == SNAPSHOT_SUCCESS


# --- FBIL --------------------------------------------------------------------------------------

def test_parse_fbil_real_fixture():
    assert parse_fbil(FBIL) == [(date(2026, 10, 8), 96.7733), (date(2026, 10, 9), 96.6149)]


def test_parse_fbil_skips_bad_rows_and_rejects_junk():
    content = (
        b'[{"processRunDate":"2026-10-09 00:00:00","subProdName":"INR / 1 USD","rate":"x"},'
        b'{"processRunDate":"bad","subProdName":"INR / 1 USD","rate":90},{"subProdName":"INR / 1 USD"},'
        b'{"processRunDate":"2026-10-09 00:00:00","subProdName":"INR / 1 EUR","rate":108},'
        b'{"processRunDate":"2026-10-09 00:00:00","subProdName":"INR / 1 USD","rate":-1},'
        b'{"processRunDate":"2026-10-10 00:00:00","subProdName":"INR / 1 USD","rate":95.5}]'
    )
    assert parse_fbil(content) == [(date(2026, 10, 10), 95.5)]
    for junk in (b"", b"nope", b'{"a":1}'):
        with pytest.raises(DatasetError, match="malformed"):
            parse_fbil(junk)


@respx.mock
async def test_fetch_fbil_stores_reference_rates(db_session, datasets_tmp):
    respx.get(fbil.URL).mock(return_value=httpx.Response(200, content=FBIL))
    snapshot = await fetch_fbil(db_session)
    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.row_count == 2
    rows = (await db_session.execute(select(FxReferenceIndia).order_by(FxReferenceIndia.rate_date))).scalars().all()
    assert [(r.rate_date, r.inr_per_usd) for r in rows] == [(date(2026, 10, 8), 96.7733), (date(2026, 10, 9), 96.6149)]
    assert snapshot.details == {"first_date": "2026-10-08", "last_date": "2026-10-09"}


@respx.mock
async def test_fetch_fbil_fails_without_usd_rows_and_on_http_errors(db_session, datasets_tmp):
    respx.get(fbil.URL).mock(return_value=httpx.Response(200, content=b"[]"))
    snapshot = await fetch_fbil(db_session)
    assert snapshot.status == SNAPSHOT_FAILED and "no USD/INR" in snapshot.error
    respx.get(fbil.URL).mock(return_value=httpx.Response(404))
    assert (await fetch_fbil(db_session)).status == SNAPSHOT_FAILED

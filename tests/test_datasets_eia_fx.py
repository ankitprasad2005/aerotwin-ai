import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from app.datasets import common, fx
from app.datasets.common import DatasetError
from app.datasets.eia import URL as EIA_URL
from app.datasets.eia import fetch_eia, parse_eia_xls
from app.datasets.fx import fetch_fx, parse_frankfurter, series_url
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, FuelPrice, FxRate

FIXTURES = Path(__file__).parent / "fixtures" / "datasets"
EIA = (FIXTURES / "eia_jet_fuel_excerpt.xls").read_bytes()
EIA_EDGE = (FIXTURES / "eia_edge_cases.xls").read_bytes()
EIA_NO_SHEET = (FIXTURES / "eia_no_data_sheet.xls").read_bytes()
FX = (FIXTURES / "frankfurter_usd_inr.json").read_bytes()


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


# --- EIA ---------------------------------------------------------------------------------------


def test_parse_eia_real_excerpt():
    series, prices = parse_eia_xls(EIA)
    assert series == "EER_EPJK_PF4_RGC_DPG"
    assert len(prices) == 12
    assert prices == sorted(prices)
    assert all(isinstance(d, date) and p > 0 for d, p in prices)
    assert prices[-1][0] >= date(2026, 1, 1)


def test_parse_eia_skips_bad_rows_and_dedupes_dates():
    series, prices = parse_eia_xls(EIA_EDGE)
    # Blank price, text price, non-date, and non-positive price are skipped; the duplicate date keeps the later value.
    assert [p for _, p in prices] == [2.6, 2.75]
    assert prices[0][0] == date(2023, 3, 15)  # Excel serial 45000


def test_parse_eia_rejects_workbook_without_data_sheet():
    with pytest.raises(DatasetError, match="Data 1"):
        parse_eia_xls(EIA_NO_SHEET)


@pytest.mark.parametrize("junk", [b"", b"not an xls file", b"\xd0\xcf\x11\xe0" + b"\x00" * 10])
def test_parse_eia_rejects_unreadable_input(junk):
    with pytest.raises(DatasetError, match="unreadable"):
        parse_eia_xls(junk)


@respx.mock
async def test_fetch_eia_upserts_prices(db_session, tmp_path):
    respx.get(EIA_URL).mock(return_value=httpx.Response(200, content=EIA))

    snap = await fetch_eia(db_session, base_dir=tmp_path)
    again = await fetch_eia(db_session, base_dir=tmp_path)  # idempotent

    assert snap.status == again.status == SNAPSHOT_SUCCESS
    assert snap.row_count == 12 and snap.details["series"] == "EER_EPJK_PF4_RGC_DPG"
    assert Path(snap.local_path).read_bytes() == EIA
    stored = (await db_session.execute(select(FuelPrice))).scalars().all()
    assert len(stored) == 12


@respx.mock
async def test_fetch_eia_with_no_usable_prices_fails(db_session, tmp_path):
    respx.get(EIA_URL).mock(return_value=httpx.Response(200, content=EIA_NO_SHEET))
    snap = await fetch_eia(db_session, base_dir=tmp_path)
    assert snap.status == SNAPSHOT_FAILED and "Data 1" in snap.error


@respx.mock
async def test_fetch_eia_http_error_is_a_failed_snapshot(db_session, tmp_path):
    respx.get(EIA_URL).mock(return_value=httpx.Response(500))
    snap = await fetch_eia(db_session, base_dir=tmp_path)
    assert snap.status == SNAPSHOT_FAILED and snap.row_count == 0


# --- Frankfurter -------------------------------------------------------------------------------


def test_parse_frankfurter_real_excerpt():
    base, rates = parse_frankfurter(FX)
    assert base == "USD"
    assert len(rates) == 8
    assert rates == sorted(rates)
    assert all(rate > 50 for _, rate in rates)


def test_parse_frankfurter_skips_malformed_entries():
    payload = {
        "base": "USD",
        "rates": {
            "2026-01-02": {"INR": 90.5},
            "2026-01-03": {"INR": "bad"},
            "not-a-date": {"INR": 91.0},
            "2026-01-04": {"EUR": 0.9},
            "2026-01-05": {"INR": 0},
            "2026-01-06": None,
            "2026-01-07": {"INR": 92},
        },
    }
    base, rates = parse_frankfurter(json.dumps(payload).encode())
    assert rates == [(date(2026, 1, 2), 90.5), (date(2026, 1, 7), 92.0)]


@pytest.mark.parametrize("junk", [b"", b"<html>", b"[]", b'{"rates": 5}', b'{"nope": 1}'])
def test_parse_frankfurter_rejects_malformed_documents(junk):
    with pytest.raises(DatasetError, match="malformed"):
        parse_frankfurter(junk)


def test_series_url_covers_the_last_120_days():
    assert series_url(date(2026, 10, 15)) == "https://api.frankfurter.dev/v1/2026-06-17..?base=USD&symbols=INR"


@respx.mock
async def test_fetch_fx_upserts_rates(db_session, tmp_path):
    route = respx.get(url__regex=r"https://api\.frankfurter\.dev/v1/.*").mock(return_value=httpx.Response(200, content=FX))

    snap = await fetch_fx(db_session, base_dir=tmp_path)
    again = await fetch_fx(db_session, base_dir=tmp_path)

    assert route.called
    assert snap.status == again.status == SNAPSHOT_SUCCESS and snap.row_count == 8
    stored = (await db_session.execute(select(FxRate))).scalars().all()
    assert len(stored) == 8 and {r.quote for r in stored} == {"INR"} and {r.base for r in stored} == {"USD"}


@respx.mock
async def test_fetch_fx_with_no_rates_fails(db_session, tmp_path):
    respx.get(url__regex=r"https://api\.frankfurter\.dev/v1/.*").mock(
        return_value=httpx.Response(200, json={"base": "USD", "rates": {}})
    )
    snap = await fetch_fx(db_session, base_dir=tmp_path)
    assert snap.status == SNAPSHOT_FAILED and "no rates" in snap.error


@respx.mock
async def test_fetch_fx_timeout_is_a_failed_snapshot(db_session, tmp_path):
    respx.get(url__regex=r"https://api\.frankfurter\.dev/v1/.*").mock(side_effect=httpx.ReadTimeout("t"))
    snap = await fetch_fx(db_session, base_dir=tmp_path)
    assert snap.status == SNAPSHOT_FAILED
    assert fx.SOURCE == snap.source

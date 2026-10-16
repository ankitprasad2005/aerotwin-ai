from datetime import date
from pathlib import Path

import httpx
import respx
from sqlalchemy import select

from app.datasets import brent
from app.datasets.eia import parse_eia_xls
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, OilPrice

BRENT = (Path(__file__).parent / "fixtures" / "datasets" / "eia_brent_excerpt.xls").read_bytes()


def test_the_real_brent_excerpt_parses_with_the_jet_fuel_parser():
    series, prices = parse_eia_xls(BRENT)
    assert series == brent.DEFAULT_SERIES == "RBRTE"
    assert len(prices) == 12 and prices == sorted(prices)
    assert prices[-1] == (date(2026, 10, 14), 126.55)


@respx.mock
async def test_fetch_brent_upserts_prices_with_the_snapshot(db_session, tmp_path):
    respx.get(brent.URL).mock(return_value=httpx.Response(200, content=BRENT))

    snap = await brent.fetch_brent(db_session, base_dir=tmp_path)
    again = await brent.fetch_brent(db_session, base_dir=tmp_path)  # idempotent

    assert snap.source == "eia_brent" and snap.status == again.status == SNAPSHOT_SUCCESS
    assert snap.row_count == 12 and snap.details["last_date"] == "2026-10-14"
    assert Path(snap.local_path).read_bytes() == BRENT
    stored = (await db_session.execute(select(OilPrice))).scalars().all()
    assert len(stored) == 12 and {r.snapshot_id for r in stored} == {again.id}


@respx.mock
async def test_fetch_brent_http_error_is_a_failed_snapshot(db_session, tmp_path):
    respx.get(brent.URL).mock(return_value=httpx.Response(500))
    snap = await brent.fetch_brent(db_session, base_dir=tmp_path)
    assert snap.status == SNAPSHOT_FAILED and snap.row_count == 0


@respx.mock
async def test_fetch_brent_without_prices_fails(db_session, tmp_path, monkeypatch):
    respx.get(brent.URL).mock(return_value=httpx.Response(200, content=BRENT))
    monkeypatch.setattr(brent, "parse_eia_xls", lambda content: ("RBRTE", []))
    snap = await brent.fetch_brent(db_session, base_dir=tmp_path)
    assert snap.status == SNAPSHOT_FAILED and "no usable prices" in snap.error

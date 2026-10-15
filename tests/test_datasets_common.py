import hashlib
from datetime import datetime, timezone

import httpx
import pytest
import respx
from sqlalchemy import select

from app.datasets import common
from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw
from app.models.external import (
    SNAPSHOT_FAILED,
    SNAPSHOT_FALLBACK,
    SNAPSHOT_SUCCESS,
    DatasetSnapshot,
    FuelPrice,
)

URL = "https://example.test/data.bin"


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(common, "_sleep", fake_sleep)
    return sleeps


@respx.mock
async def test_download_returns_the_body():
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"hello"))
    assert await download(URL) == b"hello"


@respx.mock
async def test_download_retries_server_errors_then_succeeds(no_backoff):
    route = respx.get(URL).mock(side_effect=[httpx.Response(500), httpx.Response(503), httpx.Response(200, content=b"ok")])
    assert await download(URL) == b"ok"
    assert route.call_count == 3
    assert no_backoff == [1.0, 2.0]


@respx.mock
async def test_download_retries_429():
    route = respx.get(URL).mock(side_effect=[httpx.Response(429), httpx.Response(200, content=b"ok")])
    assert await download(URL) == b"ok"
    assert route.call_count == 2


@respx.mock
async def test_download_does_not_retry_client_errors():
    route = respx.get(URL).mock(return_value=httpx.Response(404))
    with pytest.raises(DatasetError, match="404"):
        await download(URL)
    assert route.call_count == 1


@respx.mock
async def test_download_gives_up_after_the_retry_budget_on_timeouts():
    route = respx.get(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(DatasetError, match="failed"):
        await download(URL, retries=3)
    assert route.call_count == 3


@respx.mock
async def test_download_with_zero_retries_still_tries_once():
    route = respx.get(URL).mock(return_value=httpx.Response(500))
    with pytest.raises(DatasetError):
        await download(URL, retries=0)
    assert route.call_count == 1


@respx.mock
async def test_download_uses_and_keeps_open_a_supplied_client():
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"x"))
    async with httpx.AsyncClient() as client:
        assert await download(URL, client=client) == b"x"
        assert not client.is_closed


def test_save_raw_writes_under_source_and_date(tmp_path):
    now = datetime(2026, 10, 15, 8, 30, tzinfo=timezone.utc)
    path = save_raw("fx", "usd_inr.json", b"{}", now=now, base=tmp_path)
    assert path == str(tmp_path / "fx" / "2026-10-15" / "usd_inr.json")
    assert (tmp_path / "fx" / "2026-10-15" / "usd_inr.json").read_bytes() == b"{}"


def test_save_raw_defaults_to_the_configured_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "get_settings", lambda: type("S", (), {"datasets_dir": str(tmp_path)})())
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert save_raw("eia_jet_fuel", "a.xls", b"1", now=now).startswith(str(tmp_path))


def test_sha256_hex():
    assert common.sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()


async def test_run_source_records_a_success_snapshot(db_session):
    async def impl(snapshot):
        return FetchOutcome(row_count=7, local_path="/x", checksum="abc", details={"k": 1})

    snap = await run_source(db_session, "fx", "https://u", impl)

    assert snap.status == SNAPSHOT_SUCCESS
    assert (snap.row_count, snap.local_path, snap.checksum, snap.details) == (7, "/x", "abc", {"k": 1})
    assert snap.source_url == "https://u"
    assert snap.fetched_at is not None and snap.error is None


async def test_run_source_can_record_a_fallback_snapshot(db_session):
    async def impl(snapshot):
        return FetchOutcome(row_count=2, status=SNAPSHOT_FALLBACK, error="parse failed")

    snap = await run_source(db_session, "dgca", "https://u", impl)
    assert (snap.status, snap.error) == (SNAPSHOT_FALLBACK, "parse failed")


async def test_run_source_failure_rolls_back_partial_writes_and_records_failed(db_session):
    async def impl(snapshot):
        db_session.add(FuelPrice(series="s", price_date=datetime(2026, 1, 1).date(), usd_per_gallon=1.0))
        await db_session.flush()
        raise DatasetError("boom " + "x" * 2000)

    snap = await run_source(db_session, "eia_jet_fuel", "https://u", impl)

    assert snap.status == SNAPSHOT_FAILED
    assert snap.error.startswith("DatasetError: boom")
    assert len(snap.error) == common.MAX_ERROR_CHARS
    assert snap.row_count == 0
    assert (await db_session.execute(select(FuelPrice))).scalars().all() == []
    snapshots = (await db_session.execute(select(DatasetSnapshot))).scalars().all()
    assert [s.status for s in snapshots] == [SNAPSHOT_FAILED]  # the optimistic row was rolled back too
    # The session is still usable afterwards.
    assert (await db_session.execute(select(FuelPrice))).scalars().all() == []


async def test_bulk_upsert_inserts_updates_and_chunks(db_session, monkeypatch):
    from datetime import date

    monkeypatch.setattr(common, "UPSERT_CHUNK", 2)
    rows = [{"series": "s", "price_date": date(2026, 1, d), "usd_per_gallon": float(d)} for d in range(1, 6)]
    assert await bulk_upsert(db_session, FuelPrice, rows, conflict_columns=["series", "price_date"], update_columns=["usd_per_gallon"]) == 5

    rows[0]["usd_per_gallon"] = 99.0
    await bulk_upsert(db_session, FuelPrice, rows, conflict_columns=["series", "price_date"], update_columns=["usd_per_gallon"])

    stored = (await db_session.execute(select(FuelPrice).order_by(FuelPrice.price_date))).scalars().all()
    assert [p.usd_per_gallon for p in stored] == [99.0, 2.0, 3.0, 4.0, 5.0]


async def test_bulk_upsert_with_no_rows_is_a_noop(db_session):
    assert await bulk_upsert(db_session, FuelPrice, [], conflict_columns=["series", "price_date"], update_columns=[]) == 0

"""IMD warnings: parsing the real NDMA SACHET capture, the fetcher, the evidence provider and the migration."""
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.datasets import common, imd
from app.datasets.common import DatasetError, utcnow
from app.datasets.refresh import FETCHERS, SOURCE_INFO
from app.datasets.weather_evidence import MAX_IMD_WARNINGS, imd_warnings
from app.evidence.base import EvidenceRequest
from app.evidence.catalog import EVIDENCE_PROVIDERS
from app.evidence.reliability import SOURCE_RELIABILITY
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, DatasetSnapshot, ImdWarning
from tests.conftest import TEST_DATABASE_URL

SACHET = (Path(__file__).parent / "fixtures" / "datasets" / "ndma_sachet_alerts.json").read_bytes()
IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


def _entry(**overrides):
    base = {
        "severity": "WATCH", "identifier": 1792161914002027, "effective_start_time": "Fri Oct 16 20:13:00 IST 2026",
        "effective_end_time": "Fri Oct 16 23:13:00 IST 2026", "disaster_type": "Thunderstorm", "area_description": "Dumka",
        "severity_level": "Likely", "actual_lang": "en", "warning_message": "Thunderstorm is likely.", "severity_color": "orange",
        "centroid": "87.54,25.07", "alert_source": "IMD Ranchi",
    }
    return {**base, **overrides}


def test_parse_keeps_only_imd_issued_alerts_of_the_real_capture():
    rows = imd.parse_imd_warnings(SACHET)

    raw = json.loads(SACHET)
    assert 0 < len(rows) < len(raw)
    assert {r["issuer"] for r in rows} <= {e["alert_source"] for e in raw if e["alert_source"].startswith("IMD")}
    assert all(r["issuer"].startswith("IMD") and r["effective_end"] > r["effective_start"] for r in rows)
    ranchi = next(r for r in rows if r["issuer"] == "IMD Ranchi")
    assert ranchi["identifier"] == "1792161914002027" and ranchi["event"] == "Light Thunderstorm with surface wind"
    assert ranchi["effective_start"] == datetime(2026, 10, 16, 20, 13, tzinfo=IST) and ranchi["severity_color"] == "yellow"
    assert ranchi["severity_level"] == "Likely" and ranchi["language"] == "en"
    assert (ranchi["latitude"], ranchi["longitude"]) == pytest.approx((25.0704, 87.5449), abs=1e-3)


def test_parse_skips_unusable_entries_and_defaults_odd_values():
    rows = imd.parse_imd_warnings(
        json.dumps(
            [
                _entry(identifier=1),
                _entry(identifier=2, alert_source="Kerala SDMA"),
                _entry(identifier=3, effective_start_time="soon"),
                _entry(identifier=4, warning_message=""),
                _entry(identifier=None),
                "junk",
                _entry(identifier=6, severity_color="PURPLE", centroid="nope", actual_lang=None, severity_level=None),
                _entry(identifier=1, disaster_type="Rain"),  # same alert again: the last one wins
            ]
        ).encode()
    )

    assert [r["identifier"] for r in rows] == ["1", "6"]
    assert rows[0]["event"] == "Rain"
    assert rows[1]["severity_color"] == "yellow" and rows[1]["latitude"] is None and rows[1]["language"] == "en"
    assert rows[1]["severity_level"] is None


@pytest.mark.parametrize("payload", [b"", b"nope", b'{"a": 1}'])
def test_parse_rejects_malformed_documents(payload):
    with pytest.raises(DatasetError, match="malformed"):
        imd.parse_imd_warnings(payload)


@respx.mock
async def test_fetch_stores_the_imd_warnings_and_is_idempotent(db_session, tmp_path):
    respx.get(imd.FEED_URL).mock(return_value=httpx.Response(200, content=SACHET))

    snapshot = await imd.fetch_imd(db_session, base_dir=tmp_path)
    again = await imd.fetch_imd(db_session, base_dir=tmp_path)

    expected = len(imd.parse_imd_warnings(SACHET))
    assert snapshot.status == again.status == SNAPSHOT_SUCCESS and snapshot.row_count == expected
    assert snapshot.source == "imd" and "IMD Ranchi" in snapshot.details["issuers"]
    assert (tmp_path / "imd").exists()
    stored = (await db_session.execute(select(ImdWarning))).scalars().all()
    assert len(stored) == expected and all(w.snapshot_id == again.id for w in stored)


@respx.mock
async def test_fetch_with_no_imd_alert_is_an_empty_success(db_session, tmp_path):
    respx.get(imd.FEED_URL).mock(return_value=httpx.Response(200, content=b"[]"))

    snapshot = await imd.fetch_imd(db_session, base_dir=tmp_path)

    assert snapshot.status == SNAPSHOT_SUCCESS and snapshot.row_count == 0


@respx.mock
@pytest.mark.parametrize("response", [httpx.Response(401, text="IP needs to be whitelisted"), httpx.Response(200, content=b"<html>")])
async def test_fetch_failure_is_a_failed_snapshot(db_session, tmp_path, response):
    respx.get(imd.FEED_URL).mock(return_value=response)

    snapshot = await imd.fetch_imd(db_session, base_dir=tmp_path)

    assert snapshot.status == SNAPSHOT_FAILED and (await db_session.execute(select(ImdWarning))).scalars().all() == []


def test_imd_is_a_registered_source():
    assert FETCHERS["imd"] is imd.fetch_imd
    assert "SACHET" in SOURCE_INFO["imd"]["description"] and SOURCE_INFO["imd"]["source_url"] == imd.FEED_URL
    assert SOURCE_RELIABILITY["imd"] == 0.9 and EVIDENCE_PROVIDERS["imd_warnings"] is imd_warnings


def _warning(identifier, color="yellow", end_hours=2, message="x", **kw):
    now = utcnow()
    values = dict(
        identifier=identifier, issuer="IMD Chennai", event="Moderate Rain", severity_color=color, severity_level="Likely", area="Chennai",
        message=message, language="en", effective_start=now - timedelta(hours=1), effective_end=now + timedelta(hours=end_hours),
    )
    return ImdWarning(**{**values, **kw})


async def test_imd_warnings_evidence_lists_active_warnings_most_severe_first(db_session):
    request = EvidenceRequest(agent_type="WEATHER", objective="x", route=None)
    assert await imd_warnings(db_session, request) == []

    snapshot = DatasetSnapshot(source="imd", fetched_at=utcnow(), status=SNAPSHOT_SUCCESS, source_url="x", row_count=1)
    db_session.add(snapshot)
    await db_session.flush()
    db_session.add_all(
        [
            _warning("1", "yellow"), _warning("2", "red", message="y" * 400), _warning("3", "orange"), _warning("4", "red", end_hours=-1),
            _warning("5", "mystery"),
        ]
    )
    await db_session.flush()

    items = await imd_warnings(db_session, request)

    assert [i.id for i in items] == ["imd:2", "imd:3", "imd:1", "imd:5"]  # the ended red warning is gone
    first = items[0]
    assert first.source == "imd" and first.kind == "dataset" and first.reliability == 0.9 and first.url == imd.IMD_PAGE_URL
    assert first.title == "IMD red warning: Moderate Rain (IMD Chennai)"
    assert first.content["message"].endswith("...") and len(first.content["message"]) == 300
    assert first.content["area"] == "Chennai" and first.content["likelihood"] == "Likely"
    assert items[1].content["message"] == "x" and first.content["valid_to"] > first.content["valid_from"]


async def test_imd_warnings_evidence_is_capped(db_session):
    db_session.add_all([_warning(str(i)) for i in range(MAX_IMD_WARNINGS + 5)])
    await db_session.flush()

    items = await imd_warnings(db_session, EvidenceRequest(agent_type="NETWORK", objective="x", route=None))

    assert len(items) == MAX_IMD_WARNINGS == 10


# --- migration ---------------------------------------------------------------------------------------------------------

ADMIN_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
PREVIOUS_REVISION = "d3f5a7c9e1b4"


def _alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "AEROTWIN_DATABASE_URL": database_url}
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True, env=env, capture_output=True)


@pytest.fixture
async def scratch_db():
    name = f"aerotwin_migration_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = TEST_DATABASE_URL.rsplit("/", 1)[0] + f"/{name}"
    engine = create_async_engine(url)
    yield url, engine
    await engine.dispose()
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    await admin.dispose()


async def _exists(engine) -> bool:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT to_regclass('imd_warnings')"))).scalar() is not None


async def test_migration_creates_and_drops_the_imd_warnings_table(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", PREVIOUS_REVISION)
    assert not await _exists(engine)

    _alembic(url, "upgrade", "a4d9f1c3e7b5")
    assert await _exists(engine)

    _alembic(url, "downgrade", PREVIOUS_REVISION)
    assert not await _exists(engine)

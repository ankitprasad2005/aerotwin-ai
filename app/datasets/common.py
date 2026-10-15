"""Shared plumbing for the dataset fetchers: HTTP with retries, raw-file storage, snapshot bookkeeping."""
import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, DatasetSnapshot
from app.seed.data import AIRPORTS

logger = logging.getLogger(__name__)

# The airports of the digital twin; OpenFlights routes are kept only between these.
TWIN_AIRPORTS: frozenset[str] = frozenset(a["code"] for a in AIRPORTS)

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_RETRIES = 3
USER_AGENT = "Mozilla/5.0 (compatible; AeroTwinAI/1.0; dataset refresh)"
# Rows per INSERT; keeps each statement far below PostgreSQL's 32767 bind-parameter limit.
UPSERT_CHUNK = 1000
MAX_ERROR_CHARS = 500


class DatasetError(Exception):
    """A dataset could not be downloaded or parsed."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status >= 500 or status == 429
    return isinstance(exc, httpx.HTTPError)


async def download(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    retries: int = DEFAULT_RETRIES,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    backoff: float = 1.0,
) -> bytes:
    """GET `url` and return the body. Retries transport errors, 5xx and 429 up to `retries` attempts in total.

    4xx responses are not retried (they will not improve). Raises DatasetError once attempts run out.
    """
    owns_client = client is None
    http = client or httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )
    last: Exception | None = None
    try:
        for attempt in range(1, max(retries, 1) + 1):
            try:
                response = await http.get(url, timeout=timeout)
                response.raise_for_status()
                return response.content
            except httpx.HTTPError as exc:
                last = exc
                if not _is_retryable(exc):
                    break
                logger.warning("download %s failed (attempt %d/%d): %r", url, attempt, retries, exc)
                if attempt < retries:
                    await _sleep(backoff * attempt)
    finally:
        if owns_client:
            await http.aclose()
    raise DatasetError(f"download of {url} failed: {last!r}")


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def datasets_dir(base: Path | str | None = None) -> Path:
    return Path(base if base is not None else get_settings().datasets_dir)


def save_raw(source: str, filename: str, content: bytes, *, now: datetime, base: Path | str | None = None) -> str:
    """Write the downloaded bytes to <datasets_dir>/<source>/<YYYY-MM-DD>/<filename>; return the path."""
    target_dir = datasets_dir(base) / source / now.strftime("%Y-%m-%d")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    target.write_bytes(content)
    return str(target)


@dataclass
class FetchOutcome:
    """What a fetcher's `impl` reports back to run_source for the snapshot row."""

    row_count: int
    local_path: str | None = None
    checksum: str | None = None
    status: str = SNAPSHOT_SUCCESS
    error: str | None = None
    details: dict = field(default_factory=dict)


async def run_source(
    db: AsyncSession,
    source: str,
    source_url: str,
    impl: Callable[[DatasetSnapshot], Awaitable[FetchOutcome]],
    *,
    now: datetime | None = None,
) -> DatasetSnapshot:
    """Run one fetcher and record its snapshot. Never raises for a fetch problem.

    `impl` runs in a savepoint together with the snapshot row, so a failure rolls back its partial writes
    (previous good rows survive) and a FAILED snapshot is recorded instead.
    """
    fetched_at = now or utcnow()
    try:
        async with db.begin_nested():
            snapshot = DatasetSnapshot(
                source=source, fetched_at=fetched_at, status=SNAPSHOT_SUCCESS, source_url=source_url, row_count=0, details={}
            )
            db.add(snapshot)
            await db.flush()
            outcome = await impl(snapshot)
            snapshot.row_count = outcome.row_count
            snapshot.local_path = outcome.local_path
            snapshot.checksum = outcome.checksum
            snapshot.status = outcome.status
            snapshot.error = outcome.error
            snapshot.details = outcome.details
        return snapshot
    except Exception as exc:  # noqa: BLE001 - any fetch/parse/DB problem becomes a FAILED snapshot
        logger.warning("dataset %s refresh failed: %r", source, exc)
        failed = DatasetSnapshot(
            source=source,
            fetched_at=fetched_at,
            status=SNAPSHOT_FAILED,
            source_url=source_url,
            row_count=0,
            error=f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS],
            details={},
        )
        db.add(failed)
        await db.flush()
        return failed


async def bulk_upsert(
    db: AsyncSession,
    model,
    rows: Sequence[dict],
    *,
    conflict_columns: Sequence[str],
    update_columns: Iterable[str],
) -> int:
    """INSERT .. ON CONFLICT DO UPDATE in chunks; returns the number of rows submitted."""
    update_columns = list(update_columns)
    for start in range(0, len(rows), UPSERT_CHUNK):
        chunk = rows[start : start + UPSERT_CHUNK]
        stmt = pg_insert(model).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=list(conflict_columns),
            set_={
                **{column: getattr(stmt.excluded, column) for column in update_columns},
                "updated_at": utcnow(),
            },
        )
        await db.execute(stmt)
    return len(rows)

"""India Meteorological Department (IMD) weather warnings and nowcasts.

IMD's own machine APIs (mausam.imd.gov.in/api/...) answer 401 "IP needs to be whitelisted" for ordinary clients, and its
public CAP RSS (cap-sources.s3.amazonaws.com/in-imd-en/rss.xml, WMO Alert Hub) is empty most of the time. The one open,
unauthenticated machine-readable channel is the National Disaster Management Authority's SACHET CAP alert feed
(https://sachet.ndma.gov.in, public domain), which carries the district nowcasts and warnings IMD's regional centres
issue ("IMD Chennai", "IMD Ranchi", ...) next to state and flood authorities' alerts. We keep only the IMD-issued ones.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw, sha256_hex, utcnow
from app.models.external import DatasetSnapshot, ImdWarning

SOURCE = "imd"
FEED_URL = "https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails"
IMD_PAGE_URL = "https://mausam.imd.gov.in/"
ISSUER_PREFIX = "IMD"
IST = timezone(timedelta(hours=5, minutes=30))
TIME_FORMAT = "%a %b %d %H:%M:%S IST %Y"  # e.g. "Fri Oct 16 20:40:00 IST 2026"
SEVERITY_ORDER = {"red": 0, "orange": 1, "yellow": 2, "green": 3}


def _time(value) -> datetime | None:
    try:
        return datetime.strptime(str(value), TIME_FORMAT).replace(tzinfo=IST)
    except ValueError:
        return None


def _text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _centroid(value) -> tuple[float | None, float | None]:
    """(latitude, longitude) from the feed's "lon,lat" centroid string."""
    try:
        longitude, latitude = (float(part) for part in str(value).split(","))
        return latitude, longitude
    except ValueError:
        return None, None


def parse_imd_warnings(content: bytes) -> list[dict]:
    """The IMD-issued entries of the SACHET feed as ImdWarning rows; unusable entries are skipped."""
    try:
        payload = json.loads(content)
        if not isinstance(payload, list):
            raise TypeError("response is not a list")
    except (ValueError, TypeError) as exc:
        raise DatasetError(f"IMD warnings response is malformed: {exc!r}") from exc
    rows: dict[str, dict] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        issuer = _text(entry.get("alert_source"))
        identifier = _text(str(entry["identifier"])) if entry.get("identifier") is not None else None
        event, area, message = _text(entry.get("disaster_type")), _text(entry.get("area_description")), _text(entry.get("warning_message"))
        start, end = _time(entry.get("effective_start_time")), _time(entry.get("effective_end_time"))
        if not issuer or not issuer.startswith(ISSUER_PREFIX) or None in (identifier, event, area, message, start, end):
            continue
        latitude, longitude = _centroid(entry.get("centroid"))
        color = str(entry.get("severity_color") or "").lower()
        rows[identifier] = {
            "identifier": identifier,
            "issuer": issuer,
            "event": event,
            "severity_color": color if color in SEVERITY_ORDER else "yellow",
            "severity_level": _text(entry.get("severity_level")),
            "area": area,
            "message": message,
            "language": _text(entry.get("actual_lang")) or "en",
            "effective_start": start,
            "effective_end": end,
            "latitude": latitude,
            "longitude": longitude,
        }
    return list(rows.values())


async def fetch_imd(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    now = utcnow()

    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        content = await download(FEED_URL, client=client)
        path = save_raw(SOURCE, "warnings.json", content, now=now, base=base_dir)
        rows = parse_imd_warnings(content)  # no IMD warning at the moment is a valid, empty answer
        if rows:
            await bulk_upsert(
                db,
                ImdWarning,
                [{**row, "snapshot_id": snapshot.id} for row in rows],
                conflict_columns=["identifier"],
                update_columns=[
                    "issuer", "event", "severity_color", "severity_level", "area", "message", "language",
                    "effective_start", "effective_end", "latitude", "longitude", "snapshot_id",
                ],
            )
        return FetchOutcome(
            row_count=len(rows), local_path=path, checksum=sha256_hex(content), details={"issuers": sorted({r["issuer"] for r in rows})}
        )

    return await run_source(db, SOURCE, FEED_URL, impl, now=now)

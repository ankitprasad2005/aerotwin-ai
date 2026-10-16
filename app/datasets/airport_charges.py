"""Airport charges (landing, parking/housing, passenger fees) of the twin's airports, from AERA tariff orders.

The Airports Economic Regulatory Authority publishes each airport's tariff rate card as a scanned PDF annexure
to its tariff order, so the figures are not machine-readable and live parsing would be unreliable. The curated,
version-controlled CSV `fallback/airport_charges.csv` is therefore the source of truth: every row was read from
the cited order and carries its URL, document title, page and effective dates. Anything that could not be
verified in an official document is absent (never estimated). A refresh loads the CSV and records a FALLBACK
snapshot, which is how the API and the evidence report that the data is curated rather than downloaded.
"""
import csv
import logging
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, run_source, sha256_hex
from app.models.external import SNAPSHOT_FALLBACK, AirportCharge, DatasetSnapshot

logger = logging.getLogger(__name__)

SOURCE = "airport_charges"
SOURCE_URL = "https://www.aera.gov.in/tariff-orders"
CURATED_CSV = Path(__file__).parent / "fallback" / "airport_charges.csv"
CURATED_NOTE = (
    "curated from AERA tariff orders (scanned PDF annexures are not machine-readable); "
    "loaded from fallback/airport_charges.csv"
)

_REQUIRED = ("airport", "charge_type", "basis", "rate_inr", "effective_from", "source_url", "source_title")
_FLOATS = (
    "slab_from_tonnes", "slab_to_tonnes", "base_inr", "rate_inr", "hour_from", "hour_to", "rate_multiplier",
    "free_hours", "standard_added_hours",
)
_TEXT_DEFAULTS = {"stand_type": "all", "aircraft_class": "all", "applies_to": "domestic", "currency": "INR"}
_NULLABLE_TEXT = ("mt_rounding", "hour_rounding", "page", "notes")
_FLOAT_DEFAULTS = {"slab_from_tonnes": 0.0, "hour_from": 0.0, "rate_multiplier": 1.0}


def _float(value: str, column: str, line: int) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise DatasetError(f"airport charges CSV line {line}: {column} is not a number: {value!r}") from exc


def _date(value: str, column: str, line: int) -> date | None:
    if not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise DatasetError(f"airport charges CSV line {line}: {column} is not an ISO date: {value!r}") from exc


def load_curated(path: Path | str = CURATED_CSV) -> list[dict]:
    """Rows of the curated CSV as typed dicts (one per AirportCharge). Raises DatasetError on a bad file or row.

    A row must cite its source (URL and document title), name an effective date and carry a rate: unverified
    figures are meant to be left out of the file, so a row that lacks any of these is an error, not skipped.
    """
    path = Path(path)
    if not path.exists():
        raise DatasetError(f"airport charges CSV not found: {path}")
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for line, record in enumerate(csv.DictReader(handle), start=2):
            for column in _REQUIRED:
                if not (record.get(column) or "").strip():
                    raise DatasetError(f"airport charges CSV line {line}: {column} is required")
            row: dict = {c: (record.get(c) or "").strip() for c in ("airport", "charge_type", "basis", "source_url", "source_title")}
            row["airport"] = row["airport"].upper()
            for column, default in _TEXT_DEFAULTS.items():
                row[column] = (record.get(column) or "").strip() or default
            for column in _NULLABLE_TEXT:
                row[column] = (record.get(column) or "").strip() or None
            for column in _FLOATS:
                value = _float(record.get(column, ""), column, line)
                row[column] = _FLOAT_DEFAULTS.get(column) if value is None else value
            row["effective_from"] = _date(record["effective_from"], "effective_from", line)
            row["effective_to"] = _date(record.get("effective_to") or "", "effective_to", line)
            rows.append(row)
    if not rows:
        raise DatasetError(f"airport charges CSV has no rows: {path}")
    return rows


async def fetch_airport_charges(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir=None, csv_path: Path | str = CURATED_CSV
) -> DatasetSnapshot:
    """Load the curated CSV into airport_charges (replacing its rows) and record a FALLBACK snapshot.

    `client` and `base_dir` are accepted for the common fetcher signature; nothing is downloaded.
    """
    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        rows = load_curated(csv_path)
        await db.execute(delete(AirportCharge))
        db.add_all(AirportCharge(**row, snapshot_id=snapshot.id) for row in rows)
        await db.flush()
        return FetchOutcome(
            row_count=len(rows),
            local_path=str(csv_path),
            checksum=sha256_hex(Path(csv_path).read_bytes()),
            status=SNAPSHOT_FALLBACK,
            error=CURATED_NOTE,
            details={
                "airports": sorted({r["airport"] for r in rows}),
                "documents": len({r["source_url"] for r in rows}),
            },
        )

    return await run_source(db, SOURCE, SOURCE_URL, impl)


async def charge_rows(db: AsyncSession, airport: str | None = None) -> list[AirportCharge]:
    """Stored charge rows (optionally one airport), in a stable order."""
    stmt = select(AirportCharge)
    if airport:
        stmt = stmt.where(AirportCharge.airport == airport.upper())
    stmt = stmt.order_by(
        AirportCharge.airport, AirportCharge.charge_type, AirportCharge.stand_type, AirportCharge.aircraft_class,
        AirportCharge.effective_from, AirportCharge.slab_from_tonnes, AirportCharge.hour_from,
    )
    return list((await db.execute(stmt)).scalars().all())

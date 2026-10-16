"""OurAirports open data (public domain) for every Indian aerodrome: airports, runways and frequency counts."""
import csv
import io
import re
from collections import Counter
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw, sha256_hex, utcnow
from app.models.external import DatasetSnapshot, IndiaAirport, IndiaRunway

SOURCE = "ourairports_india"
BASE_URL = "https://davidmegginson.github.io/ourairports-data"
AIRPORTS_URL = f"{BASE_URL}/airports.csv"
RUNWAYS_URL = f"{BASE_URL}/runways.csv"
FREQUENCIES_URL = f"{BASE_URL}/airport-frequencies.csv"
COUNTRY = "IN"

_ICAO = re.compile(r"^[A-Z]{4}$")

AIRPORT_COLUMNS = [
    "icao_code", "iata_code", "name", "airport_type", "municipality", "latitude_deg", "longitude_deg", "elevation_ft",
    "scheduled_service", "frequency_count", "snapshot_id",
]
RUNWAY_COLUMNS = [
    "airport_ident", "length_ft", "width_ft", "surface", "lighted", "closed", "le_ident", "he_ident", "snapshot_id",
]


def _text(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _number(value: str | None) -> float | None:
    try:
        return float((value or "").strip())
    except ValueError:
        return None


def _rows(content: bytes, label: str, required: set[str]) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise DatasetError(f"OurAirports {label} CSV is missing columns {sorted(missing)}")
    return list(reader)


def parse_airports(content: bytes) -> list[dict]:
    """Indian rows (iso_country IN) of airports.csv, with the OurAirports id kept as `_ref` for the joins."""
    airports: list[dict] = []
    for row in _rows(content, "airports", {"id", "ident", "type", "name", "iso_country"}):
        if row["iso_country"] != COUNTRY or not _text(row["ident"]):
            continue
        ident = row["ident"].strip()
        icao = _text(row.get("icao_code")) or (ident if _ICAO.match(ident) else None)
        airports.append(
            {
                "_ref": row["id"],
                "ident": ident,
                "icao_code": icao,
                "iata_code": _text(row.get("iata_code")),
                "name": row["name"].strip(),
                "airport_type": row["type"].strip(),
                "municipality": _text(row.get("municipality")),
                "latitude_deg": _number(row.get("latitude_deg")),
                "longitude_deg": _number(row.get("longitude_deg")),
                "elevation_ft": _number(row.get("elevation_ft")),
                "scheduled_service": (row.get("scheduled_service") or "").strip().lower() == "yes",
            }
        )
    return airports


def parse_runways(content: bytes, idents: set[str]) -> list[dict]:
    """Runways of the given airport idents; rows without a numeric id are skipped."""
    runways: list[dict] = []
    for row in _rows(content, "runways", {"id", "airport_ident", "length_ft"}):
        if row["airport_ident"] not in idents or not row["id"].strip().isdigit():
            continue
        runways.append(
            {
                "ourairports_id": int(row["id"]),
                "airport_ident": row["airport_ident"],
                "length_ft": _number(row.get("length_ft")),
                "width_ft": _number(row.get("width_ft")),
                "surface": _text(row.get("surface")),
                "lighted": (row.get("lighted") or "").strip() == "1",
                "closed": (row.get("closed") or "").strip() == "1",
                "le_ident": _text(row.get("le_ident")),
                "he_ident": _text(row.get("he_ident")),
            }
        )
    return runways


def count_frequencies(content: bytes) -> Counter:
    """Frequencies per OurAirports airport id (airport_ref)."""
    return Counter(row["airport_ref"] for row in _rows(content, "frequencies", {"airport_ref"}))


def parse_ourairports(airports_csv: bytes, runways_csv: bytes, frequencies_csv: bytes) -> tuple[list[dict], list[dict]]:
    """(airports, runways) of India; each airport carries its `frequency_count`."""
    airports = parse_airports(airports_csv)
    if not airports:
        raise DatasetError("OurAirports airports.csv has no Indian airports")
    frequencies = count_frequencies(frequencies_csv)
    for airport in airports:
        airport["frequency_count"] = frequencies.get(airport.pop("_ref"), 0)
    runways = parse_runways(runways_csv, {a["ident"] for a in airports})
    return airports, runways


async def fetch_ourairports(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        now = utcnow()
        contents = {}
        path = None
        for filename, url in (
            ("airports.csv", AIRPORTS_URL), ("runways.csv", RUNWAYS_URL), ("airport-frequencies.csv", FREQUENCIES_URL),
        ):
            contents[filename] = await download(url, client=client)
            path = save_raw(SOURCE, filename, contents[filename], now=now, base=base_dir)
        airports, runways = parse_ourairports(
            contents["airports.csv"], contents["runways.csv"], contents["airport-frequencies.csv"]
        )
        for row in (*airports, *runways):
            row["snapshot_id"] = snapshot.id
        await bulk_upsert(db, IndiaAirport, airports, conflict_columns=["ident"], update_columns=AIRPORT_COLUMNS)
        await bulk_upsert(db, IndiaRunway, runways, conflict_columns=["ourairports_id"], update_columns=RUNWAY_COLUMNS)
        return FetchOutcome(
            row_count=len(airports) + len(runways),
            local_path=path,
            checksum=sha256_hex(b"".join(contents[name] for name in sorted(contents))),
            details={"airports": len(airports), "runways": len(runways)},
        )

    return await run_source(db, SOURCE, AIRPORTS_URL, impl)

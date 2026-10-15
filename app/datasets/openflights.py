"""OpenFlights: which airlines fly each twin route (routes.dat joined with airlines.dat)."""
import csv
import io
from pathlib import Path

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import (
    TWIN_AIRPORTS,
    DatasetError,
    FetchOutcome,
    download,
    run_source,
    save_raw,
    sha256_hex,
    utcnow,
)
from app.models.external import DatasetSnapshot, MarketRoute

SOURCE = "openflights"
BASE_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/"
ROUTES_URL = BASE_URL + "routes.dat"
AIRLINES_URL = BASE_URL + "airlines.dat"
NULL = "\\N"


def _clean(value: str) -> str | None:
    value = value.strip()
    return None if value in ("", NULL) else value


def parse_airlines(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return (name by OpenFlights airline id, name by IATA/ICAO code). Active airlines win a code clash."""
    by_id: dict[str, str] = {}
    by_code: dict[str, str] = {}
    active_codes: set[str] = set()
    for fields in csv.reader(io.StringIO(text)):
        if len(fields) < 8:
            continue  # malformed row
        airline_id, name = _clean(fields[0]), _clean(fields[1])
        if airline_id is None or name is None or name == "Unknown":
            continue
        by_id[airline_id] = name
        active = fields[7].strip() == "Y"
        for code in (_clean(fields[3]), _clean(fields[4])):
            if code is None or code == "-":
                continue
            if code not in by_code or (active and code not in active_codes):
                by_code[code] = name
            if active:
                active_codes.add(code)
    return by_id, by_code


def parse_routes(
    text: str, airlines_by_id: dict[str, str], airlines_by_code: dict[str, str], airports: frozenset[str] = TWIN_AIRPORTS
) -> list[dict]:
    """Operating routes whose origin and destination are both in `airports`, one row per airline and pair."""
    rows: dict[tuple[str, str, str], dict] = {}
    for fields in csv.reader(io.StringIO(text)):
        if len(fields) < 9:
            continue  # malformed row
        code, airline_id = _clean(fields[0]), _clean(fields[1])
        origin, destination = fields[2].strip(), fields[4].strip()
        if code is None or origin not in airports or destination not in airports or origin == destination:
            continue
        if fields[6].strip() == "Y":
            continue  # a codeshare listing: the marketing carrier does not operate the flight
        try:
            stops = int(fields[7])
        except ValueError:
            continue
        key = (airline_id or code, origin, destination)
        if key in rows:
            continue
        name = airlines_by_id.get(airline_id) if airline_id else None
        rows[key] = {
            "airline_code": code,
            "airline_name": name or airlines_by_code.get(code),
            "origin": origin,
            "destination": destination,
            "stops": stops,
            "equipment": (_clean(fields[8]) or ""),
        }
    return list(rows.values())


async def fetch_openflights(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        now = utcnow()
        routes_bytes = await download(ROUTES_URL, client=client)
        airlines_bytes = await download(AIRLINES_URL, client=client)
        routes_path = save_raw(SOURCE, "routes.dat", routes_bytes, now=now, base=base_dir)
        save_raw(SOURCE, "airlines.dat", airlines_bytes, now=now, base=base_dir)
        by_id, by_code = parse_airlines(airlines_bytes.decode("utf-8", errors="replace"))
        rows = parse_routes(routes_bytes.decode("utf-8", errors="replace"), by_id, by_code)
        if not rows:
            raise DatasetError("routes.dat contained no routes between the twin airports")
        await db.execute(delete(MarketRoute))
        db.add_all(MarketRoute(snapshot_id=snapshot.id, **row) for row in rows)
        await db.flush()
        return FetchOutcome(
            row_count=len(rows),
            local_path=routes_path,
            checksum=sha256_hex(routes_bytes),
            details={"airlines_checksum": sha256_hex(airlines_bytes), "license": "ODbL"},
        )

    return await run_source(db, SOURCE, ROUTES_URL, impl)

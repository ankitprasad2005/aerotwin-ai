"""FAA airworthiness directives (ADs) for the twin's aircraft types, via the Federal Register API (no key needed)."""
import json
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw, sha256_hex, utcnow
from app.models.external import AirworthinessDirective, DatasetSnapshot

SOURCE = "faa_airworthiness_directives"
API_URL = "https://www.federalregister.gov/api/v1/documents.json"
DOCS_URL = "https://www.federalregister.gov/documents/search?conditions%5Bagencies%5D%5B%5D=federal-aviation-administration"
# One search per manufacturer/model family of the twin's fleet (A320, A321, B737).
SEARCH_TERMS = ("Airbus A320", "Airbus A321", "Boeing 737")
WINDOW_DAYS = 365
PER_PAGE = 100
MAX_PAGES = 5  # per search term; 365 days of ADs for one family is well under 500 documents

TITLE_PREFIX = "airworthiness directives"
# Twin aircraft type -> (manufacturer word that must be in the AD title, pattern that must be in title/abstract).
TYPE_RULES: dict[str, tuple[str, re.Pattern]] = {
    "A320": ("airbus", re.compile(r"\bA320")),
    "A321": ("airbus", re.compile(r"\bA321")),
    "B737": ("boeing", re.compile(r"\b737\b")),
}


def aircraft_types_for(title: str, abstract: str | None) -> list[str]:
    """The twin aircraft types an FAA document concerns, in A320, A321, B737 order ([] when none).

    Deterministic rule: the document must be an airworthiness directive (its title starts with
    "Airworthiness Directives"), and its title must name the manufacturer ("Airbus SAS Airplanes" or
    "The Boeing Company Airplanes"). It concerns A320 when the abstract (or title) mentions a model
    starting with "A320" (A320-214, "A320 series" ...), A321 for "A321", and B737 for the model number
    "737" (737-8, 737-800, 737 MAX ...). Mentions of other models (A318, A319, 777 ...) add nothing.
    """
    if not title.lower().startswith(TITLE_PREFIX):
        return []
    text = f"{title} {abstract or ''}"
    return [
        aircraft_type
        for aircraft_type, (manufacturer, pattern) in TYPE_RULES.items()
        if manufacturer in title.lower() and pattern.search(text)
    ]


def search_url(term: str, since: date, page: int = 1) -> str:
    params = [
        ("conditions[agencies][]", "federal-aviation-administration"),
        ("conditions[type][]", "RULE"),
        ("conditions[term]", term),
        ("conditions[publication_date][gte]", since.isoformat()),
        ("order", "newest"),
        ("per_page", str(PER_PAGE)),
        *[("fields[]", f) for f in ("document_number", "title", "publication_date", "html_url", "abstract")],
    ]
    if page > 1:
        params.append(("page", str(page)))
    return f"{API_URL}?{urlencode(params)}"


def _payload(content: bytes) -> dict:
    try:
        payload = json.loads(content)
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise TypeError("no results list")
    except (ValueError, TypeError) as exc:
        raise DatasetError(f"Federal Register response is malformed: {exc!r}") from exc
    return payload


def parse_directives(content: bytes, today: date) -> list[dict]:
    """ADs of the last 365 days (up to `today`'s window start) that concern a twin aircraft type; others are skipped."""
    since = today - timedelta(days=WINDOW_DAYS)
    rows = []
    for entry in _payload(content)["results"]:
        if not isinstance(entry, dict):
            continue
        number, title, url = entry.get("document_number"), entry.get("title"), entry.get("html_url")
        abstract = entry.get("abstract")
        if not (isinstance(number, str) and number and isinstance(title, str) and isinstance(url, str)):
            continue
        try:
            published = date.fromisoformat(str(entry.get("publication_date")))
        except ValueError:
            continue
        types = aircraft_types_for(title, abstract if isinstance(abstract, str) else None)
        if published < since or not types:
            continue
        rows.append(
            {
                "document_number": number,
                "title": title,
                "publication_date": published,
                "html_url": url,
                "abstract": abstract if isinstance(abstract, str) else None,
                "aircraft_types": types,
            }
        )
    return rows


async def fetch_airworthiness_directives(
    db: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    base_dir: Path | str | None = None,
    today: date | None = None,
) -> DatasetSnapshot:
    now = utcnow()
    today = today or now.date()
    since = today - timedelta(days=WINDOW_DAYS)

    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        by_number: dict[str, dict] = {}
        digests = []
        for index, term in enumerate(SEARCH_TERMS):
            page, total_pages = 1, 1
            while page <= min(total_pages, MAX_PAGES):
                content = await download(search_url(term, since, page), client=client)
                saved = save_raw(SOURCE, f"federal_register_{index}_{page}.json", content, now=now, base=base_dir)
                digests.append(sha256_hex(content))
                total_pages = _payload(content).get("total_pages") or 1
                for row in parse_directives(content, today):
                    by_number.setdefault(row["document_number"], row)
                page += 1
        if not by_number:
            raise DatasetError("Federal Register returned no airworthiness directives for the twin's aircraft types")
        rows = sorted(by_number.values(), key=lambda r: (r["publication_date"], r["document_number"]), reverse=True)
        await bulk_upsert(
            db,
            AirworthinessDirective,
            [{**row, "snapshot_id": snapshot.id} for row in rows],
            conflict_columns=["document_number"],
            update_columns=["title", "publication_date", "html_url", "abstract", "aircraft_types", "snapshot_id"],
        )
        by_type = {t: sum(1 for r in rows if t in r["aircraft_types"]) for t in TYPE_RULES}
        return FetchOutcome(
            row_count=len(rows),
            local_path=str(Path(saved).parent),
            checksum=sha256_hex("".join(digests).encode()),
            details={"by_type": by_type, "newest": rows[0]["publication_date"].isoformat(), "since": since.isoformat()},
        )

    return await run_source(db, SOURCE, DOCS_URL, impl, now=now)

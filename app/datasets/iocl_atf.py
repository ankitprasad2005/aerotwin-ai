"""Indian Oil Corporation (IOCL) ATF prices for the four metros, from iocl.com/prices-of-petroleum-products.

The page has two ATF tables: INR per kilolitre for scheduled domestic airlines ("domestic") and USD per
kilolitre for domestic airlines on an international run ("international"). Each is headed "Last updated on
<date>"; the price is effective from the first of that month until IOCL revises it.

iocl.com sits behind a Sucuri JavaScript challenge (HTTP 307 with a script instead of the page) that a plain HTTP
client cannot pass, and this fetcher does not try to defeat it. When the live page is the challenge or has no ATF
table, the newest Internet Archive capture of the same page is used instead (real IOCL HTML; the capture time is
recorded in the snapshot details as `via="wayback"`). If neither works the snapshot is FAILED: no number is invented.
IOCL's "Previous Prices" history pages are not parsed (they are behind the same challenge and not archived).
"""
import re
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import common
from app.datasets.common import (
    DEFAULT_RETRIES, DEFAULT_TIMEOUT_SECONDS, USER_AGENT, DatasetError, FetchOutcome, bulk_upsert, run_source, save_raw,
    sha256_hex, utcnow,
)
from app.models.external import AtfPriceIndia, DatasetSnapshot

SOURCE = "iocl_atf"
PAGE_URL = "https://iocl.com/prices-of-petroleum-products"
WAYBACK_URL = "https://web.archive.org/web/2id_/" + PAGE_URL
METROS = ("Delhi", "Kolkata", "Mumbai", "Chennai")
DOMESTIC = "domestic"
INTERNATIONAL = "international"
CHALLENGE_MARKER = "sucuri_cloudproxy_js"


def _is_challenge(response: httpx.Response) -> bool:
    return response.status_code == 307 or CHALLENGE_MARKER in response.text[:5000]


class _AtfTables(HTMLParser):
    """Collects, for every "ATF Prices in Metros ..." heading, its "Last updated on" date and its city/price rows."""

    def __init__(self) -> None:
        super().__init__()
        self.sections: list[dict] = []
        self._tag: str | None = None
        self._text = ""
        self._cells: list[str] = []
        self._current: dict | None = None

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3", "td", "th"):
            self._tag, self._text = tag, ""
        elif tag == "tr":
            self._cells = []

    def handle_data(self, data):
        if self._tag:
            self._text += data

    def handle_endtag(self, tag):
        if tag == "tr":
            if self._current is not None and len(self._cells) == 2:
                self._current["rows"].append((self._cells[0], self._cells[1]))
            return
        if tag != self._tag:
            return
        text = " ".join(self._text.split())
        self._tag = None
        if tag == "h2":
            self._current = None
            if text.startswith("ATF Prices in Metros"):
                self._current = {"title": text, "updated": None, "rows": []}
                self.sections.append(self._current)
        elif tag == "h3" and self._current is not None:
            match = re.match(r"Last updated on (.+)$", text)
            self._current["updated"] = match.group(1) if match else None
        elif tag in ("td", "th"):
            self._cells.append(text)


def _number(text: str) -> float | None:
    try:
        value = float(text.replace(",", ""))
    except ValueError:
        return None
    return value if value > 0 else None


def parse_iocl_atf(content: bytes | str) -> list[dict]:
    """Rows [{city, price_month, category, inr_per_kl, usd_per_kl}] for the metros of every ATF table on the page."""
    html = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    parser = _AtfTables()
    parser.feed(html)
    rows: list[dict] = []
    for section in parser.sections:
        title = section["title"]
        if "International Run" in title and "Dollars" in title:
            category, unit = INTERNATIONAL, "usd_per_kl"
        elif "Rupees" in title:
            category, unit = DOMESTIC, "inr_per_kl"
        else:
            continue
        try:
            updated = datetime.strptime(section["updated"] or "", "%B %d, %Y").date()
        except ValueError:
            continue
        for city, price in section["rows"]:
            value = _number(price)
            if city in METROS and value is not None:
                rows.append(
                    {
                        "city": city,
                        "price_month": date(updated.year, updated.month, 1),
                        "category": category,
                        "inr_per_kl": value if unit == "inr_per_kl" else None,
                        "usd_per_kl": value if unit == "usd_per_kl" else None,
                    }
                )
    return rows


async def _get(http: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET with retries on transport errors, 5xx and 429; returns whatever other final response it gets (e.g. 307)."""
    last: Exception | None = None
    for attempt in range(1, DEFAULT_RETRIES + 1):
        try:
            response = await http.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            last = exc
        else:
            if response.status_code < 500 and response.status_code != 429:
                return response
            last = RuntimeError(f"HTTP {response.status_code}")
        if attempt < DEFAULT_RETRIES:
            await common._sleep(attempt)
    raise DatasetError(f"download of {url} failed: {last!r}")


async def fetch_iocl_atf(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        owns = client is None
        http = client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        try:
            live = await _get(http, PAGE_URL)
            blocked = _is_challenge(live)
            rows = [] if blocked else parse_iocl_atf(live.content)
            content, via, captured = live.content, "iocl", None
            if not rows:
                reason = "is behind a JavaScript challenge" if blocked else "had no ATF table"
                archive = await _get(http, WAYBACK_URL)
                if archive.status_code != 200:
                    raise DatasetError(
                        f"iocl.com {reason} (HTTP {live.status_code}) and the Internet Archive fallback "
                        f"returned HTTP {archive.status_code}"
                    )
                content, via = archive.content, "wayback"
                captured = archive.headers.get("memento-datetime")
                rows = parse_iocl_atf(content)
        finally:
            if owns:
                await http.aclose()
        if not rows:
            raise DatasetError("IOCL page contained no parseable ATF prices")
        path = save_raw(SOURCE, "prices_of_petroleum_products.html", content, now=utcnow(), base=base_dir)
        await bulk_upsert(
            db,
            AtfPriceIndia,
            [{**row, "snapshot_id": snapshot.id} for row in rows],
            conflict_columns=["city", "price_month", "category"],
            update_columns=["inr_per_kl", "usd_per_kl", "snapshot_id"],
        )
        months = sorted({row["price_month"] for row in rows})
        return FetchOutcome(
            row_count=len(rows),
            local_path=path,
            checksum=sha256_hex(content),
            details={
                "via": via,
                "captured_at": captured,
                "price_months": [m.isoformat() for m in months],
                "history": "not available: IOCL's previous-price pages are not fetchable",
            },
        )

    return await run_source(db, SOURCE, PAGE_URL, impl)

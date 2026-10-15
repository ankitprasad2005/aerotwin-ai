"""DGCA monthly domestic traffic: per-airline passengers, market share and load factor.

Discovery and parsing are best-effort (the DGCA portal is script-driven and its PDF layout changes). When
either fails, the figures in fallback/dgca_domestic.csv (real DGCA figures only, flagged `is_fallback`) are
loaded instead and the snapshot is FALLBACK.
"""
import asyncio
import csv
import io
import logging
import re
from pathlib import Path
from urllib.parse import unquote, urljoin

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw, sha256_hex, utcnow
from app.models.external import SNAPSHOT_FALLBACK, DatasetSnapshot, DgcaTraffic

logger = logging.getLogger(__name__)

SOURCE = "dgca"
PAGE_URL = "https://www.dgca.gov.in/digigov-portal/?page=monthlyStatistics%2F259%2F4751%2Fhtml&main259%2F4184%2Fservicename="
FALLBACK_CSV = Path(__file__).parent / "fallback" / "dgca_domestic.csv"

MONTHS = {
    name: index
    for index, names in enumerate(
        [
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",),
            ("june", "jun"), ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"),
            ("october", "oct"), ("november", "nov"), ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}
_MONTH_YEAR = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")[a-z]*[\s._,\-]*'?((?:19|20)?\d{2})\b", re.I)
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_SKIP_NAMES = ("total", "industry", "grand", "sl", "s.no", "airline", "carrier", "note", "source")


def infer_period(text: str) -> str | None:
    """'April 2026', 'Apr-26' or 'domestic_traffic_april_2026.pdf' -> '2026-04'. None when no month/year."""
    for match in _MONTH_YEAR.finditer(text):
        month = MONTHS.get(match.group(1).lower())
        year = match.group(2)
        if month is None:
            continue
        if len(year) == 2:
            year = "20" + year
        return f"{int(year):04d}-{month:02d}"
    return None


def discover_pdf(html: str, page_url: str = PAGE_URL) -> tuple[str, str] | None:
    """Pick the latest monthly domestic-traffic PDF linked from the page: (absolute url, period)."""
    best: tuple[str, str] | None = None
    for href in _HREF.findall(html):
        decoded = unquote(href).replace("&amp;", "&")
        lowered = decoded.lower()
        if ".pdf" not in lowered or "traffic" not in lowered:
            continue
        period = infer_period(decoded.rsplit("/", 1)[-1]) or infer_period(decoded)
        if period is None:
            continue
        if best is None or period > best[1]:
            best = (urljoin(page_url, href.replace("&amp;", "&")), period)
    return best


def _number(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def parse_traffic_text(text: str) -> list[dict]:
    """Parse extracted PDF text lines like 'IndiGo 8,034,000 65.0 86.3' into airline rows.

    The first whole number >= 1000 is the passenger count; the first two remaining values in 0..100 are the
    market share and load factor. Header, total and non-airline lines are skipped; a repeated airline keeps its
    first occurrence.
    """
    rows: dict[str, dict] = {}
    for line in text.splitlines():
        match = _NUMBER.search(line)
        if match is None:
            continue
        name = re.sub(r"^[\d.\s]+", "", line[: match.start()]).strip(" .:-|")  # drop a leading serial number
        if not name or not re.search(r"[A-Za-z]{2}", name) or name.lower().startswith(_SKIP_NAMES):
            continue
        passengers: int | None = None
        percentages: list[float] = []
        for token in _NUMBER.findall(line[match.start():]):
            value = _number(token)
            if value is None:
                continue
            if passengers is None and "." not in token and value >= 1000:
                passengers = int(value)
            elif 0 <= value <= 100:
                percentages.append(value)
        if passengers is None and not percentages:
            continue
        rows.setdefault(
            name,
            {
                "airline": name,
                "passengers": passengers,
                "market_share_pct": percentages[0] if percentages else None,
                "load_factor_pct": percentages[1] if len(percentages) > 1 else None,
            },
        )
    return list(rows.values())


def _pdf_text(content: bytes) -> str:
    import pdfplumber  # imported lazily: only the DGCA refresh needs it

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def load_fallback(path: Path = FALLBACK_CSV) -> list[dict]:
    """Rows from the fallback CSV (period, airline, passengers, market_share_pct, load_factor_pct, source_url)."""
    if not path.exists():
        return []
    rows: dict[tuple[str, str], dict] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            period = (record.get("period") or "").strip()
            airline = (record.get("airline") or "").strip()
            source_url = (record.get("source_url") or "").strip()
            if not (period and airline and source_url):
                continue
            rows[(period, airline)] = {
                "period": period,
                "airline": airline,
                "passengers": _optional_int(record.get("passengers")),
                "market_share_pct": _optional_float(record.get("market_share_pct")),
                "load_factor_pct": _optional_float(record.get("load_factor_pct")),
                "source_url": source_url,
                "is_fallback": True,
            }
    return list(rows.values())


def _optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return _number(value.strip())


def _optional_int(value: str | None) -> int | None:
    number = _optional_float(value)
    return None if number is None else int(number)


async def _parse_live(client: httpx.AsyncClient | None, base_dir) -> tuple[list[dict], str, str, str]:
    """Download and parse the newest report: (rows, period, checksum, local_path). Raises DatasetError."""
    html = (await download(PAGE_URL, client=client)).decode("utf-8", errors="replace")
    found = discover_pdf(html)
    if found is None:
        raise DatasetError("no monthly domestic traffic PDF found on the DGCA page")
    pdf_url, period = found
    content = await download(pdf_url, client=client)
    path = save_raw(SOURCE, f"domestic_traffic_{period}.pdf", content, now=utcnow(), base=base_dir)
    try:
        text = await asyncio.to_thread(_pdf_text, content)
    except Exception as exc:  # noqa: BLE001 - pdfplumber/pdfminer raise many types on a bad PDF
        raise DatasetError(f"DGCA PDF is unreadable: {exc!r}") from exc
    parsed = parse_traffic_text(text)
    if not parsed:
        raise DatasetError("no airline rows could be parsed from the DGCA PDF")
    rows = [{**row, "period": period, "source_url": pdf_url, "is_fallback": False} for row in parsed]
    return rows, period, sha256_hex(content), path


async def fetch_dgca(
    db: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    base_dir: Path | str | None = None,
    fallback_path: Path = FALLBACK_CSV,
) -> DatasetSnapshot:
    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        columns = ["passengers", "market_share_pct", "load_factor_pct", "source_url", "is_fallback"]
        try:
            rows, period, checksum, path = await _parse_live(client, base_dir)
        except DatasetError as exc:
            logger.warning("DGCA live fetch failed (%s); using the fallback CSV", exc)
            rows = load_fallback(fallback_path)
            if not rows:
                raise DatasetError(f"{exc}; the fallback CSV has no rows") from exc
            await bulk_upsert(db, DgcaTraffic, rows, conflict_columns=["period", "airline"], update_columns=columns)
            return FetchOutcome(
                row_count=len(rows),
                status=SNAPSHOT_FALLBACK,
                error=str(exc)[:500],
                details={"periods": sorted({r["period"] for r in rows})},
            )
        await bulk_upsert(db, DgcaTraffic, rows, conflict_columns=["period", "airline"], update_columns=columns)
        return FetchOutcome(row_count=len(rows), local_path=path, checksum=checksum, details={"period": period})

    return await run_source(db, SOURCE, PAGE_URL, impl)


"""PPAC (Petroleum Planning & Analysis Cell) Indian crude oil basket, USD per barrel, monthly.

The "International Prices of Crude Oil (Indian Basket)" page loads its table from an AJAX endpoint that takes a
financial year (April to March) and answers with one row of twelve month columns. The last four financial years
are fetched; empty months are skipped. The current month is a month-to-date average.
"""
import json
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import common
from app.datasets.common import (
    DEFAULT_RETRIES, DEFAULT_TIMEOUT_SECONDS, USER_AGENT, DatasetError, FetchOutcome, bulk_upsert, run_source, save_raw,
    sha256_hex, utcnow,
)
from app.models.external import DatasetSnapshot, IndianCrudeBasket

SOURCE = "ppac_crude_basket"
PAGE_URL = "https://ppac.gov.in/prices/international-prices-of-crude-oil"
AJAX_URL = "https://ppac.gov.in/AjaxController/getInternationalPricesCrudeOil"
FINANCIAL_YEARS = 4
# Column order of a financial year: April..December in the start year, January..March in the next one.
MONTH_COLUMNS = (
    "april", "may", "june", "july", "august", "september", "october", "november", "december", "january", "february", "march",
)


def financial_year_label(start_year: int) -> str:
    return f"{start_year}-{start_year + 1}"


def financial_years(today: date, count: int = FINANCIAL_YEARS) -> list[int]:
    """Start years (ascending) of the last `count` financial years up to the one containing `today`."""
    current = today.year if today.month >= 4 else today.year - 1
    return list(range(current - count + 1, current + 1))


def parse_ppac_icb(content: bytes | str, start_year: int) -> list[tuple[date, float]]:
    """[(first day of month, USD/bbl)] ascending for one financial year; empty months are skipped."""
    try:
        result = json.loads(content)["result"]
    except (ValueError, KeyError, TypeError) as exc:
        raise DatasetError(f"PPAC response is malformed: {exc!r}") from exc
    if not result:
        return []
    entries = result.values() if isinstance(result, dict) else result
    label = f"{start_year}-{str(start_year + 1)[2:]}"
    row = next((e for e in entries if isinstance(e, dict) and e.get("title") == label), None)
    if row is None:
        return []
    parsed = []
    for index, column in enumerate(MONTH_COLUMNS):
        value = row.get(column)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            continue
        year, month = (start_year, index + 4) if index < 9 else (start_year + 1, index - 8)
        parsed.append((date(year, month, 1), float(value)))
    return sorted(parsed)


async def _post(http: httpx.AsyncClient, start_year: int) -> bytes:
    """POST the financial-year form; retries transport errors and 5xx/429 like `common.download`."""
    data = {"financialYear": financial_year_label(start_year), "reportBy": "4", "pageId": "30"}
    last: Exception | None = None
    for attempt in range(1, DEFAULT_RETRIES + 1):
        try:
            response = await http.post(AJAX_URL, data=data, timeout=DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            last = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500 and exc.response.status_code != 429:
                break
            if attempt < DEFAULT_RETRIES:
                await common._sleep(attempt)
    raise DatasetError(f"download of {AJAX_URL} ({data['financialYear']}) failed: {last!r}")


async def fetch_ppac_crude(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        owns = client is None
        http = client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        now = utcnow()
        monthly: dict[date, float] = {}
        last_path = None
        checksums = []
        try:
            for start_year in financial_years(now.date()):
                content = await _post(http, start_year)
                last_path = save_raw(SOURCE, f"icb_{financial_year_label(start_year)}.json", content, now=now, base=base_dir)
                checksums.append(sha256_hex(content))
                monthly.update(parse_ppac_icb(content, start_year))
        finally:
            if owns:
                await http.aclose()
        if not monthly:
            raise DatasetError("PPAC response contained no Indian basket prices")
        months = sorted(monthly)
        await bulk_upsert(
            db,
            IndianCrudeBasket,
            [{"price_month": m, "usd_per_bbl": monthly[m], "snapshot_id": snapshot.id} for m in months],
            conflict_columns=["price_month"],
            update_columns=["usd_per_bbl", "snapshot_id"],
        )
        return FetchOutcome(
            row_count=len(months),
            local_path=last_path,
            checksum=sha256_hex("".join(checksums).encode()),
            details={"first_month": months[0].isoformat(), "last_month": months[-1].isoformat(), "latest_is_month_to_date": True},
        )

    return await run_source(db, SOURCE, PAGE_URL, impl)

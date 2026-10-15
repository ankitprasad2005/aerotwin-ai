"""EIA U.S. Gulf Coast kerosene-type jet fuel spot price (daily, USD per gallon), legacy .xls."""
from datetime import date
from pathlib import Path

import httpx
import xlrd
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw, sha256_hex, utcnow
from app.models.external import DatasetSnapshot, FuelPrice

SOURCE = "eia_jet_fuel"
URL = "https://www.eia.gov/dnav/pet/hist_xls/EER_EPJK_PF4_RGC_DPGd.xls"
DEFAULT_SERIES = "EER_EPJK_PF4_RGC_DPG"
SHEET = "Data 1"
FIRST_DATA_ROW = 3  # rows 0-2 hold the title, the "Sourcekey" line and the column headings


def parse_eia_xls(content: bytes) -> tuple[str, list[tuple[date, float]]]:
    """Return (series code, [(date, usd_per_gallon)]) sorted by date; blank/non-numeric/<=0 prices are skipped.

    A repeated date keeps its last value.
    """
    try:
        book = xlrd.open_workbook(file_contents=content)
    except Exception as exc:  # noqa: BLE001 - xlrd raises XLRDError, struct errors, AssertionError on junk input
        raise DatasetError(f"EIA workbook is unreadable: {exc!r}") from exc
    if SHEET not in book.sheet_names():
        raise DatasetError(f"EIA workbook has no {SHEET!r} sheet")
    sheet = book.sheet_by_name(SHEET)

    series = DEFAULT_SERIES
    if sheet.nrows > 1 and sheet.ncols > 1 and sheet.cell_value(1, 0) == "Sourcekey" and sheet.cell_value(1, 1):
        series = str(sheet.cell_value(1, 1)).strip()

    prices: dict[date, float] = {}
    for row in range(FIRST_DATA_ROW, sheet.nrows):
        if sheet.ncols < 2:
            break
        date_cell, price_cell = sheet.cell(row, 0), sheet.cell(row, 1)
        if date_cell.ctype != xlrd.XL_CELL_DATE or price_cell.ctype != xlrd.XL_CELL_NUMBER:
            continue
        if price_cell.value <= 0:
            continue
        try:
            year, month, day, *_ = xlrd.xldate_as_tuple(date_cell.value, book.datemode)
            prices[date(year, month, day)] = float(price_cell.value)
        except (ValueError, xlrd.XLDateError):
            continue
    return series, sorted(prices.items())


async def fetch_eia(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        content = await download(URL, client=client)
        path = save_raw(SOURCE, "jet_fuel_gulf_coast.xls", content, now=utcnow(), base=base_dir)
        series, prices = parse_eia_xls(content)
        if not prices:
            raise DatasetError("EIA workbook contained no usable prices")
        rows = [{"series": series, "price_date": d, "usd_per_gallon": p} for d, p in prices]
        await bulk_upsert(
            db, FuelPrice, rows, conflict_columns=["series", "price_date"], update_columns=["usd_per_gallon"]
        )
        return FetchOutcome(
            row_count=len(rows),
            local_path=path,
            checksum=sha256_hex(content),
            details={"series": series, "first_date": prices[0][0].isoformat(), "last_date": prices[-1][0].isoformat()},
        )

    return await run_source(db, SOURCE, URL, impl)

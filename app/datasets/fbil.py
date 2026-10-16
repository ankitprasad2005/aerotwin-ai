"""FBIL (Financial Benchmarks India) USD/INR reference rate.

The public site (an Angular app) reads the latest published reference rates from `refrates/fetch`: the rates of the
last two publication days for several currencies. Only the INR / 1 USD rows are kept; the series grows with each refresh.
"""
import json
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw, sha256_hex, utcnow
from app.models.external import DatasetSnapshot, FxReferenceIndia

SOURCE = "fbil_fx"
PAGE_URL = "https://www.fbil.org.in/"
URL = "https://www.fbil.org.in/wasdm/refrates/fetch?authenticated=false"
USD_ROW = "INR / 1 USD"


def parse_fbil(content: bytes | str) -> list[tuple[date, float]]:
    """[(date, INR per USD)] ascending; malformed or non-USD rows are skipped."""
    try:
        payload = json.loads(content)
        if not isinstance(payload, list):
            raise TypeError("payload is not a list")
    except (ValueError, TypeError) as exc:
        raise DatasetError(f"FBIL response is malformed: {exc!r}") from exc
    parsed: dict[date, float] = {}
    for row in payload:
        try:
            if row["subProdName"] != USD_ROW:
                continue
            rate = float(row["rate"])
            if rate > 0:
                parsed[date.fromisoformat(str(row["processRunDate"])[:10])] = rate
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(parsed.items())


async def fetch_fbil(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        content = await download(URL, client=client)
        path = save_raw(SOURCE, "reference_rates.json", content, now=utcnow(), base=base_dir)
        rates = parse_fbil(content)
        if not rates:
            raise DatasetError("FBIL response contained no USD/INR reference rates")
        await bulk_upsert(
            db,
            FxReferenceIndia,
            [{"rate_date": d, "inr_per_usd": r, "snapshot_id": snapshot.id} for d, r in rates],
            conflict_columns=["rate_date"],
            update_columns=["inr_per_usd", "snapshot_id"],
        )
        return FetchOutcome(
            row_count=len(rates),
            local_path=path,
            checksum=sha256_hex(content),
            details={"first_date": rates[0][0].isoformat(), "last_date": rates[-1][0].isoformat()},
        )

    return await run_source(db, SOURCE, URL, impl)

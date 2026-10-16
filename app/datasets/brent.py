"""EIA Europe Brent crude spot price FOB (daily, USD per barrel), RBRTE; same legacy .xls family as the jet fuel series."""
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw, sha256_hex, utcnow
from app.datasets.eia import parse_eia_xls
from app.models.external import DatasetSnapshot, OilPrice

SOURCE = "eia_brent"
URL = "https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls"
DEFAULT_SERIES = "RBRTE"


async def fetch_brent(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        content = await download(URL, client=client)
        path = save_raw(SOURCE, "brent_spot.xls", content, now=utcnow(), base=base_dir)
        series, prices = parse_eia_xls(content)
        if not prices:
            raise DatasetError("EIA Brent workbook contained no usable prices")
        rows = [
            {"series": series, "price_date": d, "usd_per_barrel": p, "snapshot_id": snapshot.id} for d, p in prices
        ]
        await bulk_upsert(
            db, OilPrice, rows, conflict_columns=["series", "price_date"], update_columns=["usd_per_barrel", "snapshot_id"]
        )
        return FetchOutcome(
            row_count=len(rows),
            local_path=path,
            checksum=sha256_hex(content),
            details={"series": series, "first_date": prices[0][0].isoformat(), "last_date": prices[-1][0].isoformat()},
        )

    return await run_source(db, SOURCE, URL, impl)

"""World Bank open data for India: air passengers, air freight and GDP growth (annual indicators)."""
import json
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw, sha256_hex, utcnow
from app.models.external import DatasetSnapshot, WorldBankIndicator

SOURCE = "world_bank"
COUNTRY = "IND"
API_ROOT = "https://api.worldbank.org/v2/country"

PASSENGERS = "IS.AIR.PSGR"
FREIGHT = "IS.AIR.GOOD.MT.K1"
GDP_GROWTH = "NY.GDP.MKTP.KD.ZG"

# indicator code -> (label, unit)
INDICATORS: dict[str, tuple[str, str]] = {
    PASSENGERS: ("Air passengers carried", "passengers"),
    FREIGHT: ("Air freight", "million ton-km"),
    GDP_GROWTH: ("GDP growth", "% per year"),
}


def indicator_url(code: str) -> str:
    return f"{API_ROOT}/{COUNTRY}/indicator/{code}?format=json&per_page=20"


def parse_world_bank(content: bytes) -> list[tuple[int, float]]:
    """Return [(year, value)] ascending by year; null or malformed observations are skipped."""
    try:
        payload = json.loads(content)
        records = payload[1]
        if not isinstance(records, list):
            raise TypeError("records is not a list")
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        raise DatasetError(f"World Bank response is malformed: {exc!r}") from exc
    values: dict[int, float] = {}
    for record in records:
        try:
            if record["value"] is None:
                continue
            values[int(record["date"])] = float(record["value"])
        except (ValueError, KeyError, TypeError):
            continue
    return sorted(values.items())


async def world_bank_latest(db: AsyncSession) -> dict[str, dict]:
    """Latest non-null year of each stored indicator: {code: {year, value, yoy_pct}}.

    yoy_pct is the percentage change against the immediately preceding calendar year, or None when that
    year is missing or zero. Indicators with no rows are absent.
    """
    rows = (
        await db.execute(select(WorldBankIndicator).order_by(WorldBankIndicator.indicator, WorldBankIndicator.year))
    ).scalars().all()
    by_indicator: dict[str, dict[int, float]] = {}
    for r in rows:
        by_indicator.setdefault(r.indicator, {})[r.year] = r.value
    result = {}
    for code, series in by_indicator.items():
        year = max(series)
        before = series.get(year - 1)
        yoy = round((series[year] / before - 1) * 100, 2) if before else None
        result[code] = {"year": year, "value": series[year], "yoy_pct": yoy}
    return result


async def fetch_world_bank(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        rows: list[dict] = []
        latest: dict[str, int] = {}
        now = utcnow()
        last_path = None
        for code in INDICATORS:
            content = await download(indicator_url(code), client=client)
            last_path = save_raw(SOURCE, f"{code}.json", content, now=now, base=base_dir)
            observations = parse_world_bank(content)
            if not observations:
                raise DatasetError(f"World Bank indicator {code} has no usable values")
            latest[code] = observations[-1][0]
            rows += [{"indicator": code, "year": y, "value": v, "snapshot_id": snapshot.id} for y, v in observations]
        await bulk_upsert(
            db, WorldBankIndicator, rows, conflict_columns=["indicator", "year"], update_columns=["value", "snapshot_id"]
        )
        return FetchOutcome(
            row_count=len(rows),
            local_path=last_path,
            checksum=sha256_hex(json.dumps(rows, sort_keys=True, default=str).encode()),
            details={"latest_year": latest},
        )

    return await run_source(db, SOURCE, indicator_url(PASSENGERS), impl)

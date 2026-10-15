"""Frankfurter (ECB reference rates): USD to INR time series."""
import json
from datetime import date, timedelta
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw, sha256_hex, utcnow
from app.models.external import DatasetSnapshot, FxRate

SOURCE = "fx"
BASE = "USD"
QUOTE = "INR"
HISTORY_DAYS = 120
API_ROOT = "https://api.frankfurter.dev/v1/"


def series_url(today: date, days: int = HISTORY_DAYS) -> str:
    return f"{API_ROOT}{(today - timedelta(days=days)).isoformat()}..?base={BASE}&symbols={QUOTE}"


def parse_frankfurter(content: bytes, quote: str = QUOTE) -> tuple[str, list[tuple[date, float]]]:
    """Return (base, [(date, rate)]) sorted ascending; malformed dates/rates are skipped."""
    try:
        payload = json.loads(content)
        rates = payload["rates"]
        base = str(payload.get("base") or BASE)
        if not isinstance(rates, dict):
            raise TypeError("rates is not an object")
    except (ValueError, KeyError, TypeError) as exc:
        raise DatasetError(f"Frankfurter response is malformed: {exc!r}") from exc
    parsed: dict[date, float] = {}
    for day, by_quote in rates.items():
        try:
            rate = float(by_quote[quote])
            if rate <= 0:
                continue
            parsed[date.fromisoformat(day)] = rate
        except (ValueError, KeyError, TypeError):
            continue
    return base, sorted(parsed.items())


async def fetch_fx(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    now = utcnow()
    url = series_url(now.date())

    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        content = await download(url, client=client)
        path = save_raw(SOURCE, "usd_inr.json", content, now=now, base=base_dir)
        base, rates = parse_frankfurter(content)
        if not rates:
            raise DatasetError("Frankfurter response contained no rates")
        rows = [{"base": base, "quote": QUOTE, "rate_date": d, "rate": r} for d, r in rates]
        await bulk_upsert(
            db, FxRate, rows, conflict_columns=["base", "quote", "rate_date"], update_columns=["rate"]
        )
        return FetchOutcome(
            row_count=len(rows),
            local_path=path,
            checksum=sha256_hex(content),
            details={"first_date": rates[0][0].isoformat(), "last_date": rates[-1][0].isoformat()},
        )

    return await run_source(db, SOURCE, url, impl, now=now)

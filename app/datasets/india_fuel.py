"""Read-side helpers for the Indian fuel price tables (ATF, crude basket, FBIL rate) shared by the twin's tools,
the evidence providers and the API.

ATF prices are revisions, not a daily series: a price recorded for `price_month` stays in effect until the next
revision, so "the price in month M" is the latest revision with price_month <= M.
"""
from datetime import date, timedelta
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import fbil, fx
from app.datasets.iocl_atf import DOMESTIC, METROS
from app.models.external import AtfPriceIndia, FxRate, FxReferenceIndia, IndianCrudeBasket

# The seed's demand period: its operating costs are anchored to the Indian ATF price of these months.
BASELINE_PERIOD = "2026-Q3"
US_GALLONS_PER_KL = 264.172052
DEFAULT_METRO = "Delhi"
# Metro whose ATF price applies to an airport: the airport's own city for the four metros, otherwise the nearest metro
# by road/air distance. Airports not listed fall back to DEFAULT_METRO.
METRO_BY_AIRPORT: dict[str, str] = {
    "DEL": "Delhi", "BOM": "Mumbai", "CCU": "Kolkata", "MAA": "Chennai",
    "BLR": "Chennai", "HYD": "Chennai", "COK": "Chennai", "TRV": "Chennai", "CJB": "Chennai", "IXM": "Chennai",
    "VTZ": "Chennai", "PNQ": "Mumbai", "GOI": "Mumbai", "AMD": "Mumbai", "NAG": "Mumbai", "IDR": "Mumbai",
    "STV": "Mumbai", "PAT": "Kolkata", "GAU": "Kolkata", "BBI": "Kolkata", "IXR": "Kolkata", "IMF": "Kolkata",
    "LKO": "Delhi", "JAI": "Delhi", "ATQ": "Delhi", "IXC": "Delhi", "SXR": "Delhi", "VNS": "Delhi", "DED": "Delhi",
}


def _today() -> date:
    return date.today()


def quarter_months(period: str) -> list[date]:
    """'2026-Q3' -> [2026-07-01, 2026-08-01, 2026-09-01]."""
    year, quarter = period.split("-Q")
    first = (int(quarter) - 1) * 3 + 1
    return [date(int(year), first + i, 1) for i in range(3)]


def metro_for_airport(code: str) -> tuple[str, str]:
    """(metro, match): match is 'origin' for a metro airport, 'nearest_metro' if mapped, else 'default_delhi'."""
    code = (code or "").upper()
    metro = METRO_BY_AIRPORT.get(code)
    if metro is None:
        return DEFAULT_METRO, "default_delhi"
    own = {"DEL", "BOM", "CCU", "MAA"}
    return metro, "origin" if code in own else "nearest_metro"


def month_start(day: date) -> date:
    return date(day.year, day.month, 1)


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


async def atf_in_effect(db: AsyncSession, city: str, month: date, category: str = DOMESTIC) -> AtfPriceIndia | None:
    """The ATF revision in effect in `month` for a city (latest price_month <= month)."""
    stmt = (
        select(AtfPriceIndia)
        .where(AtfPriceIndia.city == city, AtfPriceIndia.category == category, AtfPriceIndia.price_month <= month)
        .order_by(AtfPriceIndia.price_month.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def atf_before(db: AsyncSession, city: str, month: date, category: str = DOMESTIC) -> AtfPriceIndia | None:
    """The revision published before the one in `month` (latest price_month < month)."""
    return await atf_in_effect(db, city, month - timedelta(days=1), category)


async def atf_prices(db: AsyncSession, city: str | None, months: int, today: date | None = None) -> list[AtfPriceIndia]:
    """Revisions effective within the last `months` months, plus the one in effect at the window start per city/category.

    Ordered by city (metro order), category, price_month.
    """
    start = add_months(month_start(today or _today()), -months)
    cities = [c for c in METROS if city is None or c.lower() == city.lower()]
    rows: list[AtfPriceIndia] = []
    for name in cities:
        for category in (DOMESTIC, "international"):
            stmt = select(AtfPriceIndia).where(
                AtfPriceIndia.city == name, AtfPriceIndia.category == category, AtfPriceIndia.price_month >= start
            )
            in_window = list((await db.execute(stmt.order_by(AtfPriceIndia.price_month))).scalars().all())
            opening = await atf_in_effect(db, name, start - timedelta(days=1), category)
            rows += ([opening] if opening else []) + in_window
    return rows


async def crude_basket(db: AsyncSession, months: int, today: date | None = None) -> list[IndianCrudeBasket]:
    """Monthly basket prices of the last `months` months (ascending)."""
    start = add_months(month_start(today or _today()), -months)
    stmt = select(IndianCrudeBasket).where(IndianCrudeBasket.price_month >= start).order_by(IndianCrudeBasket.price_month)
    return list((await db.execute(stmt)).scalars().all())


async def _latest_and_average(db: AsyncSession, source: str, months: list[date]) -> tuple[tuple[float, date] | None, float | None]:
    """(latest (rate, date), average rate over the given months) of the FBIL or ECB series."""
    if source == fbil.SOURCE:
        model, day, value, extra = FxReferenceIndia, FxReferenceIndia.rate_date, FxReferenceIndia.inr_per_usd, ()
    else:
        model, day, value, extra = FxRate, FxRate.rate_date, FxRate.rate, (FxRate.base == fx.BASE, FxRate.quote == fx.QUOTE)
    latest = (await db.execute(select(value, day).where(*extra).order_by(day.desc()).limit(1))).first()
    end = add_months(months[-1], 1)
    average = (await db.execute(select(func.avg(value)).where(*extra, day >= months[0], day < end))).scalar_one_or_none()
    return ((latest[0], latest[1]) if latest else None), (float(average) if average is not None else None)


async def usd_inr_pair(db: AsyncSession, months: list[date]) -> dict | None:
    """The stored USD/INR rate now and averaged over `months`, from one source.

    FBIL (official reference rate) is preferred when it has both a latest rate and rates inside `months`; otherwise the
    ECB series; otherwise whichever source has a latest rate, with the baseline rate taken equal to it (flagged).
    """
    found = []
    for source in (fbil.SOURCE, fx.SOURCE):
        latest, average = await _latest_and_average(db, source, months)
        if latest is not None:
            found.append((source, latest, average))
    for source, latest, average in found:
        if average is not None:
            return {"source": source, "rate": latest[0], "date": latest[1], "baseline_rate": average, "baseline_is_latest": False}
    if found:
        source, latest, _ = found[0]
        return {"source": source, "rate": latest[0], "date": latest[1], "baseline_rate": latest[0], "baseline_is_latest": True}
    return None


async def india_fuel_basis(db: AsyncSession, origin_code: str, today: date | None = None) -> dict | None:
    """Indian ATF fuel basis for a route origin, or None when the data needed is missing.

    price_ratio = (ATF INR/kl now / USD/INR now) / (mean ATF INR/kl over the baseline months / mean USD/INR over them):
    how much dearer the origin metro's ATF is in USD than it was in the seed's demand period. None when the metro has
    no ATF price in effect for every baseline month, no ATF price now, or no stored USD/INR rate.
    """
    metro, match = metro_for_airport(origin_code)
    months = quarter_months(BASELINE_PERIOD)
    current = await atf_in_effect(db, metro, month_start(today or _today()))
    if current is None or current.inr_per_kl is None:
        return None
    baseline_rows = [await atf_in_effect(db, metro, m) for m in months]
    if any(r is None or r.inr_per_kl is None for r in baseline_rows):
        return None
    pair = await usd_inr_pair(db, months)
    if pair is None:
        return None
    baseline_inr = mean(r.inr_per_kl for r in baseline_rows)
    now_usd = current.inr_per_kl / pair["rate"]
    base_usd = baseline_inr / pair["baseline_rate"]
    return {
        "source": "iocl_atf",
        "city": metro,
        "city_match": match,
        "price_month": current.price_month.isoformat(),
        "inr_per_kl": current.inr_per_kl,
        "baseline_period": BASELINE_PERIOD,
        "baseline_inr_per_kl": round(baseline_inr, 2),
        "usd_inr": pair["rate"],
        "usd_inr_date": pair["date"].isoformat(),
        "usd_inr_source": pair["source"],
        "baseline_usd_inr": round(pair["baseline_rate"], 6),
        "baseline_usd_inr_is_latest": pair["baseline_is_latest"],
        "usd_per_gallon": round(now_usd / US_GALLONS_PER_KL, 4),
        "baseline_usd_per_gallon": round(base_usd / US_GALLONS_PER_KL, 4),
        "price_ratio": now_usd / base_usd,
    }

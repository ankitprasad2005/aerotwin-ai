"""India-wide view of the weather datasets: paging through every Indian airport and a network-wide summary."""
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import queries
from app.datasets.common import utcnow
from app.datasets.india_airports import INDIA_AIRPORT_INFO
from app.datasets.weather import CATEGORIES, is_disruptive_day

# An observation older than this is not "current" in the summary (METARs are issued hourly or half-hourly).
OBSERVATION_MAX_AGE = timedelta(hours=6)
WORST_AIRPORTS = 10
CATEGORY_RANK = {category: rank for rank, category in enumerate(CATEGORIES)}
DEFAULT_LIMIT = 25
MAX_LIMIT = 200


def api_entry(airport: str, data: dict) -> dict:
    """The /api/datasets/weather item of one airport: latest observation, TAF summary and 7-day forecast."""
    o, taf = data["observation"], data["taf"]
    return {
        "airport": airport,
        "icao": INDIA_AIRPORT_INFO[airport]["icao"],
        "observed_at": o.observed_at if o else None,
        "flight_category": o.flight_category if o else "UNKNOWN",
        "wind_kt": o.wind_kt if o else None,
        "gust_kt": o.gust_kt if o else None,
        "visibility_sm": o.visibility_sm if o else None,
        "ceiling_ft": o.ceiling_ft if o else None,
        "raw_text": o.raw_text if o else None,
        "taf_worst_flight_category_24h": taf.worst_flight_category_24h if taf else None,
        "taf_thunderstorm_24h": taf.thunderstorm_24h if taf else None,
        "forecast": [
            {
                "date": f.forecast_date,
                "precipitation_mm": f.precipitation_mm,
                "max_gust_kmh": f.max_gust_kmh,
                "weather_code": f.weather_code,
                "thunderstorm": f.thunderstorm,
            }
            for f in data["forecast"]
        ],
    }


def search_airports(q: str | None) -> list[str]:
    """IATA codes (sorted) of the Indian airports whose code, ICAO, name or city contains `q` (all when empty)."""
    needle = (q or "").strip().lower()
    return [
        code
        for code, info in INDIA_AIRPORT_INFO.items()
        if not needle or needle in " ".join((code, info["icao"], info["name"], info["city"])).lower()
    ]


async def india_page(db: AsyncSession, q: str | None, limit: int, offset: int) -> dict:
    codes = search_airports(q)
    page = codes[offset : offset + limit]
    by_airport = await queries.weather_for_airports(db, page)
    items = []
    for code in page:
        info = INDIA_AIRPORT_INFO[code]
        items.append(
            {
                **api_entry(code, by_airport[code]),
                "name": info["name"],
                "city": info["city"],
                "latitude": info["latitude"],
                "longitude": info["longitude"],
            }
        )
    return {"total": len(codes), "limit": limit, "offset": offset, "items": items}


async def india_summary(db: AsyncSession, now: datetime | None = None) -> dict:
    """Counts of Indian airports by current flight category, those with a thunderstorm in the 24 h TAF, and the
    worst-affected airports (current category, TAF worst category and thunderstorm, forecast disruption days).

    Only observations from the last 6 hours and TAFs still valid count; an airport without either is UNKNOWN.
    """
    now = now or utcnow()
    by_airport = await queries.weather_for_airports(db, list(INDIA_AIRPORT_INFO))
    counts = {category: 0 for category in (*CATEGORIES, "UNKNOWN")}
    thunderstorm, ranked = [], []
    metar = taf_count = forecast_count = 0
    has_data = False
    for code, data in by_airport.items():
        o, taf, days = data["observation"], data["taf"], data["forecast"]
        has_data = has_data or o is not None or taf is not None or bool(days)
        current = o.flight_category if o is not None and now - o.observed_at <= OBSERVATION_MAX_AGE else None
        taf = taf if taf is not None and taf.valid_to > now else None
        metar += current is not None
        taf_count += taf is not None
        forecast_count += bool(days)
        counts[current or "UNKNOWN"] += 1
        taf_thunderstorm = bool(taf and taf.thunderstorm_24h)
        if taf_thunderstorm:
            thunderstorm.append(code)
        taf_category = taf.worst_flight_category_24h if taf else None
        disruption_days = sum(1 for f in days if is_disruptive_day(f.precipitation_mm, f.max_gust_kmh, f.thunderstorm))
        score = (
            3 * CATEGORY_RANK.get(current, 0)
            + 2 * CATEGORY_RANK.get(taf_category, 0)
            + (2 if taf_thunderstorm else 0)
            + disruption_days
        )
        if score > 0:
            info = INDIA_AIRPORT_INFO[code]
            ranked.append(
                {
                    "airport": code,
                    "icao": info["icao"],
                    "name": info["name"],
                    "city": info["city"],
                    "flight_category": current or "UNKNOWN",
                    "taf_worst_flight_category_24h": taf_category,
                    "taf_thunderstorm_24h": taf_thunderstorm if taf else None,
                    "disruption_days": disruption_days,
                    "score": score,
                }
            )
    ranked.sort(key=lambda entry: (-entry["score"], entry["airport"]))
    return {
        "generated_at": now,
        "airports_total": len(by_airport),
        "has_data": has_data,  # any stored observation, TAF or forecast, even stale ones
        "airports_reporting": {"metar": metar, "taf": taf_count, "forecast": forecast_count},
        "by_flight_category": counts,
        "thunderstorm_24h": {"count": len(thunderstorm), "airports": thunderstorm},
        "worst_airports": ranked[:WORST_AIRPORTS],
    }

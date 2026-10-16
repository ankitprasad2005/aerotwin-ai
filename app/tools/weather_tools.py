from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import queries, weather_india
from app.datasets.weather import AIRPORT_STATIONS, DISRUPTION_GUST_KMH, DISRUPTION_PRECIPITATION_MM, is_disruptive_day  # noqa: F401
from app.models.digital_twin import Airport, Route

# HIGH when this many distinct days in the next 7 are disrupted at either end of a route.
HIGH_RISK_DISRUPTION_DAYS = 3


def weather_risk_for(
    origin_category: str,
    destination_category: str,
    disruption_days: int,
    taf_categories: Iterable[str | None] = (),
    taf_thunderstorm: bool = False,
) -> str:
    """HIGH if either end is IFR/LIFR now, disruption_days >= 3, either end's TAF has IFR/LIFR as the worst
    category of the next 24 hours, or a TAF forecasts a thunderstorm at either end in the next 24 hours;
    MODERATE if either end is MVFR or disruption_days is 1 or 2; otherwise LOW (an UNKNOWN category, a missing
    TAF or a TAF that is only MVFR adds no risk of its own)."""
    categories = {origin_category, destination_category}
    if (
        categories & {"IFR", "LIFR"}
        or disruption_days >= HIGH_RISK_DISRUPTION_DAYS
        or set(taf_categories) & {"IFR", "LIFR"}
        or taf_thunderstorm
    ):
        return "HIGH"
    if "MVFR" in categories or disruption_days >= 1:
        return "MODERATE"
    return "LOW"


def _airport_entry(airport: str, observation, forecast, taf=None) -> dict:
    disruption_dates = [
        f.forecast_date.isoformat()
        for f in forecast
        if is_disruptive_day(f.precipitation_mm, f.max_gust_kmh, f.thunderstorm)
    ]
    return {
        "airport": airport,
        "icao": AIRPORT_STATIONS[airport][0],
        "observed_at": observation.observed_at.isoformat() if observation else None,
        "flight_category": observation.flight_category if observation else "UNKNOWN",
        "wind_kt": observation.wind_kt if observation else None,
        "gust_kt": observation.gust_kt if observation else None,
        "visibility_sm": observation.visibility_sm if observation else None,
        "ceiling_ft": observation.ceiling_ft if observation else None,
        "taf_worst_flight_category_24h": taf.worst_flight_category_24h if taf else None,
        "taf_thunderstorm_24h": taf.thunderstorm_24h if taf else None,
        "forecast_days": len(forecast),
        "disruption_days": len(disruption_dates),
        "disruption_dates": disruption_dates,
        "thunderstorm_days": sum(1 for f in forecast if f.thunderstorm),
        "max_precipitation_mm": max((f.precipitation_mm for f in forecast), default=None),
        "max_gust_kmh": max((f.max_gust_kmh for f in forecast), default=None),
    }


async def query_weather_conditions(db: AsyncSession) -> dict:
    """Current conditions and the 7-day outlook per twin airport, and a precomputed weather risk per twin route.

    Per route: `disruption_days_next_7` counts the distinct forecast days on which either endpoint expects a
    thunderstorm (WMO code 95, 96 or 99), precipitation >= 20 mm or gusts >= 60 km/h. `weather_risk` is HIGH
    if either endpoint is currently IFR or LIFR, disruption_days_next_7 >= 3, either endpoint's TAF (terminal
    forecast) has IFR or LIFR as its worst flight category in the next 24 hours, or either endpoint's TAF
    forecasts a thunderstorm in the next 24 hours; MODERATE if either endpoint is MVFR or
    disruption_days_next_7 is 1 or 2; otherwise LOW. Airports without data are UNKNOWN and have
    no forecast days (see forecast_days_available) rather than any invented values.
    """
    by_airport = await queries.weather_by_airport(db)
    airports = [_airport_entry(code, data["observation"], data["forecast"], data["taf"]) for code, data in by_airport.items()]
    entry_by_code = {a["airport"]: a for a in airports}

    origin, destination = Airport.__table__.alias("o"), Airport.__table__.alias("d")
    pairs = (
        await db.execute(
            select(origin.c.code, destination.c.code)
            .select_from(
                Route.__table__.join(origin, Route.origin_id == origin.c.id).join(destination, Route.destination_id == destination.c.id)
            )
            .order_by(origin.c.code, destination.c.code)
        )
    ).all()

    routes = []
    for origin_code, destination_code in pairs:
        ends = [entry_by_code.get(origin_code), entry_by_code.get(destination_code)]
        if None in ends:  # an airport outside the weather stations: nothing to report
            continue
        start, end = ends
        dates = sorted(set(start["disruption_dates"]) | set(end["disruption_dates"]))
        taf_known = [e["taf_thunderstorm_24h"] for e in (start, end) if e["taf_thunderstorm_24h"] is not None]
        taf_thunderstorm = any(taf_known) if taf_known else None
        routes.append(
            {
                "route": f"{origin_code}-{destination_code}",
                "origin_flight_category": start["flight_category"],
                "destination_flight_category": end["flight_category"],
                "disruption_days_next_7": len(dates),
                "disruption_dates": dates,
                "origin_taf_worst_flight_category_24h": start["taf_worst_flight_category_24h"],
                "destination_taf_worst_flight_category_24h": end["taf_worst_flight_category_24h"],
                "taf_thunderstorm_24h": taf_thunderstorm,
                "forecast_days_available": min(start["forecast_days"], end["forecast_days"]),
                "weather_risk": weather_risk_for(
                    start["flight_category"],
                    end["flight_category"],
                    len(dates),
                    (start["taf_worst_flight_category_24h"], end["taf_worst_flight_category_24h"]),
                    bool(taf_thunderstorm),
                ),
            }
        )
    return {"weather": {"airports": airports, "routes": routes, "india": await _india_context(db)}}


INDIA_WORST_AIRPORTS = 5


async def _india_context(db: AsyncSession) -> dict:
    """Network-wide context for the WEATHER agent: how many Indian airports are in each current flight category,
    how many expect a thunderstorm within 24 h, and the worst-affected airports. It does not change any route risk."""
    summary = await weather_india.india_summary(db)
    return {
        "airports_total": summary["airports_total"],
        "airports_reporting": summary["airports_reporting"],
        "by_flight_category": summary["by_flight_category"],
        "thunderstorm_24h_count": summary["thunderstorm_24h"]["count"],
        "thunderstorm_24h_airports": summary["thunderstorm_24h"]["airports"],
        "worst_airports": summary["worst_airports"][:INDIA_WORST_AIRPORTS],
    }

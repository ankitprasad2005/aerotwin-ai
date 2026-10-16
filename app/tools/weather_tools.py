from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import queries
from app.datasets.weather import AIRPORT_STATIONS, DISRUPTION_GUST_KMH, DISRUPTION_PRECIPITATION_MM, is_disruptive_day  # noqa: F401
from app.models.digital_twin import Airport, Route

# HIGH when this many distinct days in the next 7 are disrupted at either end of a route.
HIGH_RISK_DISRUPTION_DAYS = 3


def weather_risk_for(origin_category: str, destination_category: str, disruption_days: int) -> str:
    """HIGH if either end is IFR/LIFR now or disruption_days >= 3; MODERATE if either end is MVFR or
    disruption_days is 1 or 2; otherwise LOW (an UNKNOWN category adds no risk of its own)."""
    categories = {origin_category, destination_category}
    if categories & {"IFR", "LIFR"} or disruption_days >= HIGH_RISK_DISRUPTION_DAYS:
        return "HIGH"
    if "MVFR" in categories or disruption_days >= 1:
        return "MODERATE"
    return "LOW"


def _airport_entry(airport: str, observation, forecast) -> dict:
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
    if either endpoint is currently IFR or LIFR or disruption_days_next_7 >= 3; MODERATE if either endpoint
    is MVFR or disruption_days_next_7 is 1 or 2; otherwise LOW. Airports without data are UNKNOWN and have
    no forecast days (see forecast_days_available) rather than any invented values.
    """
    by_airport = await queries.weather_by_airport(db)
    airports = [_airport_entry(code, data["observation"], data["forecast"]) for code, data in by_airport.items()]
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
        routes.append(
            {
                "route": f"{origin_code}-{destination_code}",
                "origin_flight_category": start["flight_category"],
                "destination_flight_category": end["flight_category"],
                "disruption_days_next_7": len(dates),
                "disruption_dates": dates,
                "forecast_days_available": min(start["forecast_days"], end["forecast_days"]),
                "weather_risk": weather_risk_for(start["flight_category"], end["flight_category"], len(dates)),
            }
        )
    return {"weather": {"airports": airports, "routes": routes}}

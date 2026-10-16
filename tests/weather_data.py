"""Helpers that put weather rows (as the fetchers would store them) into the test database."""
from datetime import date, datetime, timedelta, timezone

from app.models.external import SNAPSHOT_SUCCESS, DatasetSnapshot, WeatherForecast, WeatherObservation

OBSERVED_AT = datetime(2026, 10, 16, 11, 0, tzinfo=timezone.utc)
FIRST_DAY = date(2026, 10, 16)
QUIET_DAY = (0.0, 20.0, 1)  # precipitation mm, gust km/h, WMO code
ICAO = {"BOM": "VABB", "DEL": "VIDP", "BLR": "VOBL", "MAA": "VOMM", "HYD": "VOHS", "CCU": "VECC"}


def make_snapshot(source, minutes=0, status=SNAPSHOT_SUCCESS):
    return DatasetSnapshot(
        source=source, fetched_at=OBSERVED_AT + timedelta(minutes=minutes), status=status, source_url="https://x", row_count=1,
    )


async def add_weather(db, observations=None, forecasts=None):
    """observations: {airport: category or dict of overrides}; forecasts: {airport: {day_index: (mm, gust, code)}}.

    Every airport in `forecasts` gets 7 days, quiet except for the given day indexes.
    """
    metar, meteo = make_snapshot("aviation_weather"), make_snapshot("open_meteo")
    db.add_all([metar, meteo])
    await db.flush()
    for airport, spec in (observations or {}).items():
        fields = {"flight_category": spec} if isinstance(spec, str) else dict(spec)
        values = dict(
            airport=airport, icao=ICAO[airport], observed_at=OBSERVED_AT, flight_category="VFR", wind_kt=8.0,
            gust_kt=None, visibility_sm=6.0, ceiling_ft=None, raw_text=f"METAR {ICAO[airport]} 161100Z", snapshot_id=metar.id,
        )
        db.add(WeatherObservation(**{**values, **fields}))
    for airport, days in (forecasts or {}).items():
        for index in range(7):
            mm, gust, code = days.get(index, QUIET_DAY)
            db.add(WeatherForecast(
                airport=airport, forecast_date=FIRST_DAY + timedelta(days=index), precipitation_mm=mm, max_gust_kmh=gust,
                weather_code=code, thunderstorm=code in (95, 96, 99), snapshot_id=meteo.id,
            ))
    await db.flush()

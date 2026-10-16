"""Helpers that put airworthiness directive and TAF rows (as the fetchers would store them) into the test database."""
from datetime import date, datetime, timedelta, timezone

from app.models.external import SNAPSHOT_SUCCESS, AirworthinessDirective, DatasetSnapshot, WeatherTaf
from tests.weather_data import ICAO, OBSERVED_AT

TITLE = "Airworthiness Directives; Airbus SAS Airplanes"


async def add_directives(db, *specs):
    """specs: (document_number, days_ago, aircraft_types) or a dict of AirworthinessDirective fields."""
    snapshot = DatasetSnapshot(
        source="faa_airworthiness_directives", fetched_at=OBSERVED_AT, status=SNAPSHOT_SUCCESS, source_url="https://x", row_count=len(specs),
    )
    db.add(snapshot)
    await db.flush()
    for spec in specs:
        if isinstance(spec, dict):
            fields = spec
        else:
            number, days_ago, types = spec
            fields = dict(document_number=number, publication_date=date.today() - timedelta(days=days_ago), aircraft_types=types)
        values = dict(
            title=TITLE, html_url=f"https://www.federalregister.gov/d/{fields['document_number']}",
            abstract=f"The FAA is adopting a new AD for {fields['document_number']}.", snapshot_id=snapshot.id,
        )
        db.add(AirworthinessDirective(**{**values, **fields}))
    await db.flush()


async def add_tafs(db, tafs):
    """tafs: {airport: (worst_flight_category_24h, thunderstorm_24h)}."""
    snapshot = DatasetSnapshot(
        source="aviation_weather_taf", fetched_at=OBSERVED_AT, status=SNAPSHOT_SUCCESS, source_url="https://x", row_count=len(tafs),
    )
    db.add(snapshot)
    await db.flush()
    for airport, (category, thunderstorm) in tafs.items():
        db.add(WeatherTaf(
            airport=airport, icao=ICAO[airport], issued_at=OBSERVED_AT, valid_from=OBSERVED_AT,
            valid_to=OBSERVED_AT + timedelta(hours=30), worst_flight_category_24h=category, thunderstorm_24h=thunderstorm,
            raw_text=f"TAF {ICAO[airport]} 161100Z", snapshot_id=snapshot.id,
        ))
    await db.flush()

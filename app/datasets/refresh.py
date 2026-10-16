"""Refresh the external datasets: `refresh_all(db)` and the CLI `python -m app.datasets.refresh`."""
import argparse
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import (
    aai_traffic, airport_charges, airworthiness, brent, dgca, eia, fx, imd, openflights, opensky_live, ourairports, weather,
    world_bank,
)
from app.datasets.common import DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from app.models.external import DatasetSnapshot

logger = logging.getLogger(__name__)

Fetcher = Callable[..., Awaitable[DatasetSnapshot]]

FETCHERS: dict[str, Fetcher] = {
    openflights.SOURCE: openflights.fetch_openflights,
    eia.SOURCE: eia.fetch_eia,
    brent.SOURCE: brent.fetch_brent,
    fx.SOURCE: fx.fetch_fx,
    dgca.SOURCE: dgca.fetch_dgca,
    weather.AVIATION_WEATHER_SOURCE: weather.fetch_aviation_weather,
    weather.OPEN_METEO_SOURCE: weather.fetch_open_meteo,
    airworthiness.SOURCE: airworthiness.fetch_airworthiness_directives,
    weather.TAF_SOURCE: weather.fetch_taf,
    world_bank.SOURCE: world_bank.fetch_world_bank,
    opensky_live.SOURCE: opensky_live.fetch_opensky_live,
    ourairports.SOURCE: ourairports.fetch_ourairports,
    aai_traffic.SOURCE: aai_traffic.fetch_aai_traffic,
    imd.SOURCE: imd.fetch_imd,
    airport_charges.SOURCE: airport_charges.fetch_airport_charges,
}

# What the API lists for each source (title, description, licence, upstream URL).
SOURCE_INFO: dict[str, dict[str, str]] = {
    openflights.SOURCE: {
        "title": "OpenFlights routes",
        "description": "Airlines operating each route between the twin's airports (rival airlines).",
        "license": "Open Database License (ODbL) 1.0. Data (c) OpenFlights.org and contributors, "
        "https://openflights.org/data.html",
        "source_url": openflights.ROUTES_URL,
    },
    eia.SOURCE: {
        "title": "EIA jet fuel price",
        "description": "Daily U.S. Gulf Coast kerosene-type jet fuel spot price (USD per gallon).",
        "license": "U.S. Energy Information Administration; public domain",
        "source_url": eia.URL,
    },
    brent.SOURCE: {
        "title": "EIA Brent crude price",
        "description": "Daily Europe Brent crude spot price FOB (USD per barrel).",
        "license": "U.S. Energy Information Administration; public domain",
        "source_url": brent.URL,
    },
    fx.SOURCE: {
        "title": "USD/INR exchange rate",
        "description": "Daily USD to INR reference rate (European Central Bank data via Frankfurter).",
        "license": "Frankfurter, ECB reference rates; free to use",
        "source_url": fx.API_ROOT,
    },
    dgca.SOURCE: {
        "title": "DGCA domestic traffic",
        "description": "Monthly Indian domestic passengers, market share and load factor per airline.",
        "license": "Directorate General of Civil Aviation, Government of India; public data",
        "source_url": dgca.PAGE_URL,
    },
    weather.AVIATION_WEATHER_SOURCE: {
        "title": "Airport weather observations (METAR)",
        "description": "Current METAR reports for the twin's airports: flight category, wind, visibility and ceiling.",
        "license": "NOAA Aviation Weather Center, aviationweather.gov; U.S. Government public data",
        "source_url": weather.METAR_API,
    },
    weather.OPEN_METEO_SOURCE: {
        "title": "7-day airport weather forecast",
        "description": "Daily precipitation, peak wind gusts and thunderstorm risk for the twin's airports (Open-Meteo).",
        "license": "Open-Meteo.com weather forecast API; CC BY 4.0 for non-commercial use, attribution required",
        "source_url": weather.FORECAST_API,
    },
    airworthiness.SOURCE: {
        "title": "FAA airworthiness directives",
        "description": "Airworthiness directives (final rules) of the last 365 days that concern the twin's aircraft types "
        "(A320, A321, B737), from the Federal Register.",
        "license": "U.S. Federal Register / Federal Aviation Administration; U.S. Government public data",
        "source_url": airworthiness.DOCS_URL,
    },
    weather.TAF_SOURCE: {
        "title": "Airport terminal forecasts (TAF)",
        "description": "TAF terminal forecasts for the twin's airports, summarised as the worst flight category and "
        "thunderstorm risk over the next 24 hours.",
        "license": "NOAA Aviation Weather Center, aviationweather.gov; U.S. Government public data",
        "source_url": weather.TAF_API,
    },
    world_bank.SOURCE: {
        "title": "World Bank air transport indicators (India)",
        "description": "Annual air passengers carried, air freight (million ton-km) and GDP growth for India.",
        "license": "World Bank Open Data; CC BY 4.0",
        "source_url": world_bank.indicator_url(world_bank.PASSENGERS),
    },
    opensky_live.SOURCE: {
        "title": "Live air traffic over India (OpenSky)",
        "description": "Aircraft over India and near 32 major airports (airborne and on ground), from OpenSky state "
        "vectors; previous-day arrivals and departures of the twin's airports when OpenSky credentials are set.",
        "license": "OpenSky Network terms of use: non-profit research, education and government use; other commercial "
        "use needs OpenSky's permission. Cite Schafer et al., IPSN 2014. " + opensky_live.TERMS_URL,
        "source_url": opensky_live.states_url(),
    },
    ourairports.SOURCE: {
        "title": "India airports and runways (OurAirports)",
        "description": "Every Indian aerodrome with its codes, location, elevation, runways and frequency count.",
        "license": "OurAirports open data; public domain (https://ourairports.com/data/)",
        "source_url": ourairports.AIRPORTS_URL,
    },
    aai_traffic.SOURCE: {
        "title": "AAI airport traffic (monthly)",
        "description": "Monthly aircraft movements, passengers and freight per Indian airport, with the domestic and "
        "international split and year-on-year change (Airports Authority of India Traffic News).",
        "license": "Airports Authority of India, Government of India; published public statistics",
        "source_url": aai_traffic.INDEX_URL,
    },
    imd.SOURCE: {
        "title": "IMD weather warnings and nowcasts (India)",
        "description": "District weather warnings and nowcasts issued by India Meteorological Department centres, "
        "read from the NDMA SACHET CAP alert feed (IMD's own APIs need a whitelisted IP).",
        "license": "India Meteorological Department / National Disaster Management Authority, Government of India; public alerts",
        "source_url": imd.FEED_URL,
    },
    airport_charges.SOURCE: {
        "title": "Indian airport charges (AERA tariff orders)",
        "description": "Domestic landing, parking/housing and passenger (UDF) charges of the twin's airports, curated "
        "from AERA tariff orders; every row cites its order, page and effective date. Loaded from a curated CSV "
        "(the order annexures are scanned PDFs), so the snapshot status is FALLBACK.",
        "license": "Airports Economic Regulatory Authority of India tariff orders; public documents",
        "source_url": airport_charges.SOURCE_URL,
    },
}


def validate_sources(sources: Sequence[str] | None) -> list[str]:
    """The requested source names (all of them when None/empty); raises ValueError for an unknown name."""
    if not sources:
        return list(FETCHERS)
    unknown = [name for name in sources if name not in FETCHERS]
    if unknown:
        raise ValueError(f"unknown dataset source(s): {', '.join(unknown)}; valid: {', '.join(FETCHERS)}")
    return list(dict.fromkeys(sources))


async def refresh_all(
    db: AsyncSession, sources: Sequence[str] | None = None, *, client: httpx.AsyncClient | None = None
) -> list[DatasetSnapshot]:
    """Refresh each requested source independently (one failure never stops the others) and commit each."""
    names = validate_sources(sources)
    owns_client = client is None
    http = client or httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )
    snapshots: list[DatasetSnapshot] = []
    try:
        for name in names:
            snapshots.append(await FETCHERS[name](db, client=http))
            await db.commit()
    finally:
        if owns_client:
            await http.aclose()
    return snapshots


def format_summary(snapshots: Sequence[DatasetSnapshot]) -> str:
    lines = []
    for s in snapshots:
        line = f"{s.source:<14} {s.status:<9} rows={s.row_count}"
        if s.error:
            line += f"  ({s.error})"
        lines.append(line)
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.datasets.refresh", description="Refresh external datasets.")
    parser.add_argument("--source", action="append", dest="sources", choices=list(FETCHERS), help="repeatable; default all")
    return parser.parse_args(argv)


async def run_cli(argv: Sequence[str] | None = None, session_factory=None) -> int:
    """Run the refresh and print a summary. Exit code 1 if any source FAILED."""
    args = parse_args(argv)
    if session_factory is None:
        from app.db import async_session_factory as session_factory
    async with session_factory() as db:
        snapshots = await refresh_all(db, args.sources)
    print(format_summary(snapshots))
    return 1 if any(s.status == "FAILED" for s in snapshots) else 0


def main() -> None:  # pragma: no cover - thin process entry point
    logging.basicConfig(level=logging.INFO)
    sys.exit(asyncio.run(run_cli()))


if __name__ == "__main__":  # pragma: no cover
    main()

"""Weather for the twin's airports: METAR observations (aviationweather.gov) and a 7-day forecast (Open-Meteo)."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, FetchOutcome, bulk_upsert, download, run_source, save_raw, sha256_hex, utcnow
from app.models.external import DatasetSnapshot, WeatherForecast, WeatherObservation

AVIATION_WEATHER_SOURCE = "aviation_weather"
OPEN_METEO_SOURCE = "open_meteo"
METAR_API = "https://aviationweather.gov/api/data/metar"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 7

# IATA -> (ICAO, latitude, longitude). Coordinates are the OpenFlights airports.dat values
# (https://openflights.org/data.html), rounded to 4 decimals.
AIRPORT_STATIONS: dict[str, tuple[str, float, float]] = {
    "BOM": ("VABB", 19.0887, 72.8678),
    "DEL": ("VIDP", 28.5665, 77.1031),
    "BLR": ("VOBL", 13.1979, 77.7063),
    "MAA": ("VOMM", 12.9900, 80.1693),
    "HYD": ("VOHS", 17.2313, 78.4298),
    "CCU": ("VECC", 22.6547, 88.4467),
}
ICAO_TO_IATA = {icao: iata for iata, (icao, _, _) in AIRPORT_STATIONS.items()}

# WMO weather codes for a thunderstorm: 95 (slight/moderate), 96 and 99 (with hail).
THUNDERSTORM_CODES = frozenset({95, 96, 99})
# Cloud covers that make a ceiling (broken, overcast, obscured / vertical visibility).
CEILING_COVERS = frozenset({"BKN", "OVC", "OVX", "VV"})

CATEGORIES = ("VFR", "MVFR", "IFR", "LIFR")


def metar_url() -> str:
    return f"{METAR_API}?ids={','.join(icao for icao, _, _ in AIRPORT_STATIONS.values())}&format=json"


def forecast_url() -> str:
    latitudes = ",".join(str(lat) for _, lat, _ in AIRPORT_STATIONS.values())
    longitudes = ",".join(str(lon) for _, _, lon in AIRPORT_STATIONS.values())
    return (
        f"{FORECAST_API}?latitude={latitudes}&longitude={longitudes}"
        f"&daily=precipitation_sum,wind_gusts_10m_max,weather_code&timezone=Asia%2FKolkata&forecast_days={FORECAST_DAYS}"
    )


def flight_category_for(ceiling_ft: float | None, visibility_sm: float | None) -> str | None:
    """FAA flight category from ceiling and visibility; the worse of the two decides.

    LIFR: ceiling < 500 ft or visibility < 1 sm. IFR: ceiling 500 to < 1000 ft or visibility 1 to < 3 sm.
    MVFR: ceiling 1000 to 3000 ft or visibility 3 to 5 sm. VFR: otherwise. No ceiling means no
    restriction from clouds. None when neither value is known (nothing to base a category on).
    """
    if ceiling_ft is None and visibility_sm is None:
        return None
    ceiling = float("inf") if ceiling_ft is None else ceiling_ft
    visibility = float("inf") if visibility_sm is None else visibility_sm
    if ceiling < 500 or visibility < 1:
        return "LIFR"
    if ceiling < 1000 or visibility < 3:
        return "IFR"
    if ceiling <= 3000 or visibility <= 5:
        return "MVFR"
    return "VFR"


def _number(value) -> float | None:
    """A float from a number or a string like "10+"; None for anything else (bool and NaN included)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value.rstrip("+")) if isinstance(value, str) else float(value)
    except (ValueError, TypeError):
        return None
    return number if number == number else None


def _ceiling(clouds) -> float | None:
    bases = []
    for layer in clouds if isinstance(clouds, list) else []:
        if isinstance(layer, dict) and layer.get("cover") in CEILING_COVERS:
            base = _number(layer.get("base"))
            if base is not None:
                bases.append(base)
    return min(bases) if bases else None


def _observed_at(entry: dict) -> datetime | None:
    epoch = entry.get("obsTime")
    if isinstance(epoch, (int, float)) and not isinstance(epoch, bool):
        return datetime.fromtimestamp(epoch, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(entry["reportTime"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None


def parse_metar(content: bytes) -> list[dict]:
    """One row per twin airport (its latest report); entries that are unusable are skipped."""
    try:
        payload = json.loads(content)
        if not isinstance(payload, list):
            raise TypeError("response is not a list")
    except (ValueError, TypeError) as exc:
        raise DatasetError(f"METAR response is malformed: {exc!r}") from exc
    latest: dict[str, dict] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        icao = entry.get("icaoId")
        airport = ICAO_TO_IATA.get(icao)
        observed_at = _observed_at(entry)
        raw = entry.get("rawOb")
        if airport is None or observed_at is None or not isinstance(raw, str) or not raw:
            continue
        ceiling = _ceiling(entry.get("clouds"))
        visibility = _number(entry.get("visib"))
        # Prefer the category the source reports; otherwise compute it from ceiling/visibility (FAA thresholds).
        category = entry.get("fltCat") if entry.get("fltCat") in CATEGORIES else flight_category_for(ceiling, visibility)
        if category is None:
            continue
        row = {
            "airport": airport,
            "icao": icao,
            "observed_at": observed_at,
            "flight_category": category,
            "wind_kt": _number(entry.get("wspd")) or 0.0,
            "gust_kt": _number(entry.get("wgst")),
            "visibility_sm": visibility,
            "ceiling_ft": ceiling,
            "raw_text": raw,
        }
        if airport not in latest or observed_at > latest[airport]["observed_at"]:
            latest[airport] = row
    return list(latest.values())


def parse_open_meteo(content: bytes) -> list[dict]:
    """Forecast rows for the twin airports, in AIRPORT_STATIONS order; days with missing values are skipped."""
    try:
        payload = json.loads(content)
        locations = payload if isinstance(payload, list) else [payload]
        if len(locations) != len(AIRPORT_STATIONS):
            raise ValueError(f"expected {len(AIRPORT_STATIONS)} locations, got {len(locations)}")
        series_by_airport = [
            list(zip(d["time"], d["precipitation_sum"], d["wind_gusts_10m_max"], d["weather_code"]))
            for d in (location["daily"] for location in locations)
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise DatasetError(f"Open-Meteo response is malformed: {exc!r}") from exc
    rows: list[dict] = []
    for airport, series in zip(AIRPORT_STATIONS, series_by_airport):
        for day, precipitation, gust, code in series:
            precipitation, gust, code = _number(precipitation), _number(gust), _number(code)
            try:
                forecast_date = date.fromisoformat(day)
            except (ValueError, TypeError):
                continue
            if precipitation is None or gust is None or code is None:
                continue
            rows.append(
                {
                    "airport": airport,
                    "forecast_date": forecast_date,
                    "precipitation_mm": precipitation,
                    "max_gust_kmh": gust,
                    "weather_code": int(code),
                    "thunderstorm": int(code) in THUNDERSTORM_CODES,
                }
            )
    return rows


async def fetch_aviation_weather(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    now = utcnow()
    url = metar_url()

    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        content = await download(url, client=client)
        path = save_raw(AVIATION_WEATHER_SOURCE, "metar.json", content, now=now, base=base_dir)
        rows = parse_metar(content)
        if not rows:
            raise DatasetError("METAR response contained no observations for the twin airports")
        await bulk_upsert(
            db,
            WeatherObservation,
            [{**row, "snapshot_id": snapshot.id} for row in rows],
            conflict_columns=["airport", "observed_at"],
            update_columns=["icao", "flight_category", "wind_kt", "gust_kt", "visibility_sm", "ceiling_ft", "raw_text", "snapshot_id"],
        )
        return FetchOutcome(
            row_count=len(rows),
            local_path=path,
            checksum=sha256_hex(content),
            details={"airports": sorted(row["airport"] for row in rows)},
        )

    return await run_source(db, AVIATION_WEATHER_SOURCE, url, impl, now=now)


async def fetch_open_meteo(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    now = utcnow()
    url = forecast_url()

    async def impl(snapshot: DatasetSnapshot) -> FetchOutcome:
        content = await download(url, client=client)
        path = save_raw(OPEN_METEO_SOURCE, "forecast.json", content, now=now, base=base_dir)
        rows = parse_open_meteo(content)
        if not rows:
            raise DatasetError("Open-Meteo response contained no forecast days")
        await bulk_upsert(
            db,
            WeatherForecast,
            [{**row, "snapshot_id": snapshot.id} for row in rows],
            conflict_columns=["airport", "forecast_date"],
            update_columns=["precipitation_mm", "max_gust_kmh", "weather_code", "thunderstorm", "snapshot_id"],
        )
        dates = sorted(row["forecast_date"] for row in rows)
        return FetchOutcome(
            row_count=len(rows),
            local_path=path,
            checksum=sha256_hex(content),
            details={"first_date": dates[0].isoformat(), "last_date": dates[-1].isoformat()},
        )

    return await run_source(db, OPEN_METEO_SOURCE, url, impl, now=now)

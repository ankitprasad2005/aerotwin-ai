"""Live air traffic over India: the airport list, the nearest-airport assignment and the congestion rule.

Data comes from the OpenSky Network (see `opensky_live.py`): one snapshot of aircraft state vectors over an India
bounding box. This module holds the deterministic part that is independent of the HTTP API.

Airport assignment (haversine great-circle distance, Earth radius 6371 km):
  * each state vector is assigned to the single nearest airport of `INDIA_AIRPORTS`, and only if that airport is
    within `APPROACH_RADIUS_KM` (80 km, the approach/departure airspace);
  * an aircraft that reports `on_ground` and is within `TERMINAL_RADIUS_KM` (25 km) counts as `on_ground_nearby`
    (at the gate, taxiing or on the runway);
  * an aircraft that is airborne within the 80 km radius counts as `airborne_nearby`;
  * `aircraft_within_radius` = on_ground_nearby + airborne_nearby.
  Aircraft on the ground farther than 25 km from every airport (e.g. a helicopter pad) are not counted.

Live congestion of an airport (LOW / MODERATE / HIGH) compares its latest `aircraft_within_radius` with the median
of the airport's own previous `HISTORY_SNAPSHOTS` (12) snapshots:
  * with at least `MIN_HISTORY` (6) earlier snapshots: ratio = count / max(median, 1);
    ratio < 0.75 -> LOW, ratio > 1.25 -> HIGH, otherwise MODERATE; when the median is below `MIN_BASELINE` (2)
    the history says too little about "normal" and the fixed thresholds below are used instead;
  * otherwise fixed thresholds on the count: hubs (BOM, DEL, BLR, MAA, HYD, CCU) LOW below 8, HIGH from 20;
    all other airports LOW below 3, HIGH from 8. In between is MODERATE.
These constants are rough calibrations against the anonymous OpenSky coverage of India (terrestrial receivers
only, so counts are a lower bound of real traffic) and are a documented heuristic, not a measurement.

Airport coordinates and ICAO codes: OurAirports `airports.csv` (https://ourairports.com/data/,
https://davidmegginson.github.io/ourairports-data/airports.csv), public domain (CC0).
"""
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from statistics import median
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external import AirportTrafficLive, AirTrafficSnapshot

EARTH_RADIUS_KM = 6371.0
TERMINAL_RADIUS_KM = 25.0
APPROACH_RADIUS_KM = 80.0
HISTORY_SNAPSHOTS = 12
MIN_HISTORY = 6
MIN_BASELINE = 2
LOW_RATIO = 0.75
HIGH_RATIO = 1.25

LOW, MODERATE, HIGH = "LOW", "MODERATE", "HIGH"

HUBS: frozenset[str] = frozenset({"BOM", "DEL", "BLR", "MAA", "HYD", "CCU"})  # the twin's six airports
# (LOW below, HIGH from) on the aircraft count when there is too little history.
HUB_THRESHOLDS = (8, 20)
OTHER_THRESHOLDS = (3, 8)

# Bounding box over India and its neighbourhood: (lamin, lomin, lamax, lomax).
INDIA_BBOX = (6.0, 68.0, 36.0, 98.0)


class Airport(NamedTuple):
    iata: str
    icao: str
    lat: float
    lon: float
    city: str


# OurAirports airports.csv, India, large and medium airports; the twin's six first, then the next busiest.
INDIA_AIRPORTS: tuple[Airport, ...] = tuple(
    Airport(*row)
    for row in (
        ("BOM", "VABB", 19.0887, 72.8679, "Mumbai"),
        ("DEL", "VIDP", 28.5556, 77.0952, "New Delhi"),
        ("BLR", "VOBL", 13.1979, 77.7063, "Bengaluru"),
        ("MAA", "VOMM", 12.99, 80.1693, "Chennai"),
        ("HYD", "VOHS", 17.2313, 78.4299, "Hyderabad"),
        ("CCU", "VECC", 22.654, 88.4476, "Kolkata"),
        ("AMD", "VAAH", 23.0772, 72.6347, "Ahmedabad"),
        ("COK", "VOCI", 10.151, 76.4008, "Kochi"),
        ("PNQ", "VAPO", 18.5821, 73.9197, "Pune"),
        ("GOI", "VOGO", 15.3801, 73.8333, "Vasco da Gama"),
        ("GAU", "VEGT", 26.1067, 91.5852, "Guwahati"),
        ("JAI", "VIJP", 26.8242, 75.8122, "Jaipur"),
        ("LKO", "VILK", 26.7606, 80.8893, "Lucknow"),
        ("TRV", "VOTV", 8.4819, 76.92, "Thiruvananthapuram"),
        ("ATQ", "VIAR", 31.7096, 74.7973, "Amritsar"),
        ("IXC", "VICG", 30.6735, 76.7885, "Chandigarh"),
        ("PAT", "VEPT", 25.5913, 85.088, "Patna"),
        ("SXR", "VISR", 33.9871, 74.7742, "Srinagar"),
        ("BBI", "VEBS", 20.251, 85.8147, "Bhubaneswar"),
        ("IXR", "VERC", 23.3143, 85.3217, "Ranchi"),
        ("NAG", "VANP", 21.0922, 79.0472, "Nagpur"),
        ("IDR", "VAID", 22.7214, 75.8005, "Indore"),
        ("CJB", "VOCB", 11.03, 77.0434, "Coimbatore"),
        ("VNS", "VEBN", 25.4522, 82.8625, "Varanasi"),
        ("IXB", "VEBD", 26.6812, 88.3286, "Siliguri"),
        ("GAY", "VEGY", 24.7443, 84.9512, "Gaya"),
        ("IMF", "VEIM", 24.76, 93.8967, "Imphal"),
        ("UDR", "VAUD", 24.6177, 73.8961, "Udaipur"),
        ("VTZ", "VOVI", 17.9715, 83.5036, "Visakhapatnam"),
        ("IXM", "VOMD", 9.8345, 78.0934, "Madurai"),
        ("BDQ", "VABO", 22.3362, 73.2263, "Vadodara"),
        ("RPR", "VARP", 21.1804, 81.7388, "Raipur"),
    )
)
AIRPORTS_BY_IATA: dict[str, Airport] = {a.iata: a for a in INDIA_AIRPORTS}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def nearest_airport(
    lat: float, lon: float, airports: Sequence[Airport] = INDIA_AIRPORTS
) -> tuple[Airport, float]:
    """The nearest airport and its distance in km (ties go to the earlier airport in the list)."""
    best = min(airports, key=lambda a: haversine_km(lat, lon, a.lat, a.lon))
    return best, haversine_km(lat, lon, best.lat, best.lon)


@dataclass(frozen=True)
class StateVector:
    icao24: str
    callsign: str | None
    lat: float
    lon: float
    on_ground: bool
    baro_altitude_m: float | None = None
    velocity_ms: float | None = None


def totals(vectors: Iterable[StateVector]) -> dict[str, int]:
    vectors = list(vectors)
    on_ground = sum(1 for v in vectors if v.on_ground)
    return {"aircraft_over_india": len(vectors), "airborne": len(vectors) - on_ground, "on_ground": on_ground}


def assign_to_airports(
    vectors: Iterable[StateVector], airports: Sequence[Airport] = INDIA_AIRPORTS
) -> dict[str, dict[str, int]]:
    """Per airport IATA: aircraft_within_radius, on_ground_nearby, airborne_nearby (zeros included)."""
    counts = {a.iata: {"on_ground_nearby": 0, "airborne_nearby": 0} for a in airports}
    for v in vectors:
        airport, distance = nearest_airport(v.lat, v.lon, airports)
        if v.on_ground and distance <= TERMINAL_RADIUS_KM:
            counts[airport.iata]["on_ground_nearby"] += 1
        elif not v.on_ground and distance <= APPROACH_RADIUS_KM:
            counts[airport.iata]["airborne_nearby"] += 1
    return {
        iata: {**c, "aircraft_within_radius": c["on_ground_nearby"] + c["airborne_nearby"]} for iata, c in counts.items()
    }


def fixed_congestion(iata: str, count: int) -> str:
    low_below, high_from = HUB_THRESHOLDS if iata in HUBS else OTHER_THRESHOLDS
    if count < low_below:
        return LOW
    return HIGH if count >= high_from else MODERATE


def live_congestion(iata: str, count: int, history: Sequence[int]) -> tuple[str, float | None]:
    """(LOW|MODERATE|HIGH, baseline median or None when the fixed thresholds were used).

    `history` are the airport's earlier counts (newest first is fine); only the first HISTORY_SNAPSHOTS count.
    """
    recent = list(history)[:HISTORY_SNAPSHOTS]
    baseline = median(recent) if len(recent) >= MIN_HISTORY else None
    if baseline is None or baseline < MIN_BASELINE:
        return fixed_congestion(iata, count), None
    ratio = count / baseline
    if ratio < LOW_RATIO:
        return LOW, float(baseline)
    return (HIGH if ratio > HIGH_RATIO else MODERATE), float(baseline)


def airport_row_view(row: AirportTrafficLive, history: Sequence[int]) -> dict:
    airport = AIRPORTS_BY_IATA.get(row.airport)
    congestion, baseline = live_congestion(row.airport, row.aircraft_within_radius, history)
    return {
        "airport": row.airport,
        "icao": row.icao,
        "city": airport.city if airport else None,
        "taken_at": row.taken_at,
        "aircraft_within_radius": row.aircraft_within_radius,
        "on_ground_nearby": row.on_ground_nearby,
        "airborne_nearby": row.airborne_nearby,
        "arrivals_last_24h": row.arrivals_last_24h,
        "departures_last_24h": row.departures_last_24h,
        "live_congestion": congestion,
        "baseline_median": baseline,
        "history_samples": min(len(history), HISTORY_SNAPSHOTS),
    }


async def _history_counts(db: AsyncSession, iata: str, before) -> list[int]:
    stmt = (
        select(AirportTrafficLive.aircraft_within_radius)
        .where(AirportTrafficLive.airport == iata, AirportTrafficLive.taken_at < before)
        .order_by(AirportTrafficLive.taken_at.desc())
        .limit(HISTORY_SNAPSHOTS)
    )
    return list((await db.execute(stmt)).scalars().all())


async def latest_air_traffic(db: AsyncSession, airports: Iterable[str] | None = None) -> dict | None:
    """The newest snapshot: {taken_at, india: {...}, airports: [per-airport view with live_congestion]}.

    None when nothing is stored. `airports` (IATA codes) restricts the airport rows.
    """
    latest = (
        await db.execute(select(AirTrafficSnapshot).order_by(AirTrafficSnapshot.taken_at.desc()).limit(1))
    ).scalars().first()
    if latest is None:
        return None
    stmt = select(AirportTrafficLive).where(AirportTrafficLive.taken_at == latest.taken_at)
    if airports is not None:
        stmt = stmt.where(AirportTrafficLive.airport.in_(list(airports)))
    rows = (await db.execute(stmt)).scalars().all()
    order = {a.iata: i for i, a in enumerate(INDIA_AIRPORTS)}
    rows = sorted(rows, key=lambda r: order.get(r.airport, len(order)))
    views = [airport_row_view(r, await _history_counts(db, r.airport, r.taken_at)) for r in rows]
    return {
        "taken_at": latest.taken_at,
        "india": {
            "aircraft_over_india": latest.aircraft_over_india,
            "airborne": latest.airborne,
            "on_ground": latest.on_ground,
        },
        "airports": views,
    }


async def air_traffic_history(db: AsyncSession, airport: str | None, limit: int) -> list[dict]:
    """Newest-first stored rows: one airport's counts, or the India totals when `airport` is None."""
    if airport is None:
        stmt = select(AirTrafficSnapshot).order_by(AirTrafficSnapshot.taken_at.desc()).limit(limit)
        return [
            {
                "taken_at": r.taken_at,
                "aircraft_over_india": r.aircraft_over_india,
                "airborne": r.airborne,
                "on_ground": r.on_ground,
            }
            for r in (await db.execute(stmt)).scalars().all()
        ]
    stmt = (
        select(AirportTrafficLive)
        .where(AirportTrafficLive.airport == airport)
        .order_by(AirportTrafficLive.taken_at.desc())
        .limit(limit)
    )
    return [
        {
            "taken_at": r.taken_at,
            "airport": r.airport,
            "aircraft_within_radius": r.aircraft_within_radius,
            "on_ground_nearby": r.on_ground_nearby,
            "airborne_nearby": r.airborne_nearby,
            "arrivals_last_24h": r.arrivals_last_24h,
            "departures_last_24h": r.departures_last_24h,
        }
        for r in (await db.execute(stmt)).scalars().all()
    ]

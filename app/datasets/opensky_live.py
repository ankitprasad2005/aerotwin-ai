"""Live air traffic over India from the OpenSky Network REST API (https://openskynetwork.github.io/opensky-api/rest.html).

* `GET /api/states/all?lamin&lomin&lamax&lomax` works anonymously: the newest state vectors (10 s resolution) in the
  India bounding box. The bounding box (30 x 30 degrees) costs 4 credits; anonymous users get 400 credits per day
  (about 100 snapshots), a registered user 4,000. When the quota is exhausted the API answers 429 with
  `X-Rate-Limit-Retry-After-Seconds`; that becomes a FAILED snapshot (never retried within the run, no data invented).
* `GET /api/flights/arrival|departure?airport=<ICAO>&begin&end` is refused anonymously (403 "You cannot access
  historical flights") and, for registered users, only has data up to the end of the previous UTC day (the data is
  batch-processed at night) with an interval of at most two days. So with credentials we count the previous UTC day's
  arrivals and departures of the twin's six airports (30 credits each, once per UTC day, carried forward into the
  later snapshots of the same day); without credentials those two columns stay NULL.
* Credentials are OAuth2 client credentials (`opensky_client_id` / `opensky_client_secret` settings, blank =
  anonymous); the token (30 minutes) is requested from the OpenSky auth server for each refresh.

Terms of use: OpenSky data is licensed for non-profit research, non-profit education and government use, and
commercial internal testing/evaluation; other commercial use needs written permission from the OpenSky Network
(https://opensky-network.org/about/terms-of-use). Users are asked to cite: M. Schafer, M. Strohmeier, V. Lenders,
I. Martinovic, M. Wilhelm, "Bringing Up OpenSky: A Large-scale ADS-B Sensor Network for Research", IPSN 2014.
Coverage comes from volunteer ground receivers, so counts are a lower bound of real traffic.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.datasets.air_traffic import (
    AIRPORTS_BY_IATA, HUBS, INDIA_AIRPORTS, INDIA_BBOX, StateVector, assign_to_airports, totals,
)
from app.datasets.common import (
    DEFAULT_TIMEOUT_SECONDS, USER_AGENT, DatasetError, FetchOutcome, bulk_upsert, run_source, save_raw, sha256_hex, utcnow,
)
from app.models.external import AirportTrafficLive, AirTrafficSnapshot, DatasetSnapshot

SOURCE = "opensky_live"
API_ROOT = "https://opensky-network.org/api"
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
TERMS_URL = "https://opensky-network.org/about/terms-of-use"


def states_url() -> str:
    lamin, lomin, lamax, lomax = INDIA_BBOX
    return f"{API_ROOT}/states/all?lamin={lamin:g}&lomin={lomin:g}&lamax={lamax:g}&lomax={lomax:g}"


def flights_url(kind: str, icao: str, begin: int, end: int) -> str:
    return f"{API_ROOT}/flights/{kind}?airport={icao}&begin={begin}&end={end}"


def parse_states(content: bytes) -> tuple[datetime, list[StateVector]]:
    """(API time, state vectors with a position). Vectors without latitude/longitude are skipped."""
    try:
        payload = json.loads(content)
        taken_at = datetime.fromtimestamp(int(payload["time"]), tz=timezone.utc)
        raw = payload["states"]
        if not isinstance(raw, list):
            raise TypeError("states is not a list")
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise DatasetError(f"OpenSky states response is malformed: {exc!r}") from exc
    vectors = []
    for s in raw:
        try:
            if s[5] is None or s[6] is None:
                continue
            vectors.append(
                StateVector(
                    icao24=str(s[0]),
                    callsign=(str(s[1]).strip() or None) if s[1] is not None else None,
                    lat=float(s[6]),
                    lon=float(s[5]),
                    on_ground=bool(s[8]),
                    baro_altitude_m=float(s[7]) if s[7] is not None else None,
                    velocity_ms=float(s[9]) if s[9] is not None else None,
                )
            )
        except (IndexError, ValueError, TypeError):
            continue
    return taken_at, vectors


def previous_utc_day(now: datetime) -> tuple[int, int]:
    """(begin, end) Unix times of the whole previous UTC day, end inclusive of its last second."""
    midnight = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((midnight - timedelta(days=1)).timestamp()), int(midnight.timestamp()) - 1


async def _get(client: httpx.AsyncClient, url: str, headers: dict[str, str]) -> httpx.Response:
    try:
        return await client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise DatasetError(f"OpenSky request {url} failed: {exc!r}") from exc


def _raise_for_states(response: httpx.Response) -> None:
    if response.status_code == 429:
        wait = response.headers.get("X-Rate-Limit-Retry-After-Seconds")
        raise DatasetError(f"OpenSky rate limit reached (429); retry after {wait or 'an unknown number of'} seconds")
    if response.status_code != 200:
        raise DatasetError(f"OpenSky states request failed with HTTP {response.status_code}")


async def _access_token(client: httpx.AsyncClient, client_id: str, client_secret: str) -> str | None:
    """A bearer token, or None when the auth server refuses (the caller then stays anonymous)."""
    try:
        response = await client.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return str(response.json()["access_token"])
    except (httpx.HTTPError, ValueError, KeyError):
        return None


async def _count_flights(client: httpx.AsyncClient, kind: str, icao: str, begin: int, end: int, headers: dict) -> int | None:
    """Number of flights in the window; None when OpenSky refuses or has no data (404 = none found)."""
    try:
        response = await client.get(flights_url(kind, icao, begin, end), headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)
        if response.status_code != 200:
            return None
        flights = response.json()
        return len(flights) if isinstance(flights, list) else None
    except (httpx.HTTPError, ValueError):
        return None


async def _todays_flight_counts(db: AsyncSession, now: datetime) -> dict[str, tuple[int | None, int | None]]:
    """Counts already stored since UTC midnight, newest first wins: {iata: (arrivals, departures)}."""
    midnight = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        await db.execute(
            select(AirportTrafficLive)
            .where(AirportTrafficLive.taken_at >= midnight, AirportTrafficLive.arrivals_last_24h.is_not(None))
            .order_by(AirportTrafficLive.taken_at)
        )
    ).scalars().all()
    return {r.airport: (r.arrivals_last_24h, r.departures_last_24h) for r in rows}


async def fetch_opensky_live(
    db: AsyncSession, *, client: httpx.AsyncClient | None = None, base_dir: Path | str | None = None
) -> DatasetSnapshot:
    async def impl(snapshot: DatasetSnapshot, http: httpx.AsyncClient) -> FetchOutcome:
        settings = get_settings()
        headers: dict[str, str] = {}
        authenticated = False
        if settings.opensky_client_id and settings.opensky_client_secret:
            token = await _access_token(http, settings.opensky_client_id, settings.opensky_client_secret)
            if token:
                headers["Authorization"] = f"Bearer {token}"
                authenticated = True
        response = await _get(http, states_url(), headers)
        _raise_for_states(response)
        taken_at, vectors = parse_states(response.content)
        if not vectors:
            raise DatasetError("OpenSky returned no state vectors for the India bounding box")
        now = utcnow()
        local_path = save_raw(SOURCE, f"states_{int(taken_at.timestamp())}.json", response.content, now=now, base=base_dir)

        flights: dict[str, tuple[int | None, int | None]] = {}
        flights_note = "anonymous access: arrivals and departures are not available"
        if authenticated:
            flights = await _todays_flight_counts(db, now)
            begin, end = previous_utc_day(now)
            for iata in [a.iata for a in INDIA_AIRPORTS if a.iata in HUBS and a.iata not in flights]:
                icao = AIRPORTS_BY_IATA[iata].icao
                flights[iata] = (
                    await _count_flights(http, "arrival", icao, begin, end, headers),
                    await _count_flights(http, "departure", icao, begin, end, headers),
                )
            flights_note = "arrivals and departures counted for the previous UTC day"

        total = totals(vectors)
        await bulk_upsert(
            db, AirTrafficSnapshot, [{"taken_at": taken_at, **total, "snapshot_id": snapshot.id}],
            conflict_columns=["taken_at"], update_columns=[*total, "snapshot_id"],
        )
        counts = assign_to_airports(vectors)
        rows = [
            {
                "taken_at": taken_at,
                "airport": a.iata,
                "icao": a.icao,
                **counts[a.iata],
                "arrivals_last_24h": flights.get(a.iata, (None, None))[0],
                "departures_last_24h": flights.get(a.iata, (None, None))[1],
                "snapshot_id": snapshot.id,
            }
            for a in INDIA_AIRPORTS
        ]
        await bulk_upsert(
            db, AirportTrafficLive, rows, conflict_columns=["taken_at", "airport"],
            update_columns=[c for c in rows[0] if c not in ("taken_at", "airport")],
        )
        return FetchOutcome(
            row_count=len(rows),
            local_path=local_path,
            checksum=sha256_hex(response.content),
            details={
                "taken_at": taken_at.isoformat(),
                **total,
                "authenticated": authenticated,
                "flights": flights_note,
                "credits_remaining": response.headers.get("X-Rate-Limit-Remaining"),
            },
        )

    owns_client = client is None
    http = client or httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )
    try:
        return await run_source(db, SOURCE, states_url(), lambda snapshot: impl(snapshot, http))
    finally:
        if owns_client:
            await http.aclose()

"""Evidence provider for live air traffic (OpenSky): the route's two airports, or India totals without a route."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import opensky_live
from app.datasets.air_traffic import latest_air_traffic
from app.datasets.evidence import parse_route
from app.datasets.queries import latest_snapshot
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.reliability import SOURCE_RELIABILITY
from app.models.external import SNAPSHOT_SUCCESS

_FIELDS = (
    "aircraft_within_radius", "on_ground_nearby", "airborne_nearby", "arrivals_last_24h", "departures_last_24h",
    "live_congestion", "baseline_median",
)


async def live_air_traffic(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """Latest aircraft counts and live congestion at the route's airports, plus the India-wide totals.

    arrivals_last_24h / departures_last_24h are the previous UTC day's flights (null without OpenSky credentials).
    Returns [] when no snapshot is stored.
    """
    route = parse_route(request.route)
    data = await latest_air_traffic(db, airports=route)
    if data is None:
        return []
    snapshot = await latest_snapshot(db, opensky_live.SOURCE, status=SNAPSHOT_SUCCESS)
    taken_at = data["taken_at"]
    content: dict = {"taken_at": taken_at.isoformat(), "india": data["india"]}
    if route:
        content["route"] = f"{route[0]}-{route[1]}"
        content["airports"] = {v["airport"]: {k: v[k] for k in _FIELDS} for v in data["airports"]}
    return [
        EvidenceItem(
            id=f"traffic:opensky:{route[0] + '-' + route[1] if route else 'IN'}:{int(taken_at.timestamp())}",
            source="opensky",
            kind="dataset",
            title="Live air traffic over India (OpenSky Network)",
            url=opensky_live.states_url(),
            fetched_at=snapshot.fetched_at if snapshot else taken_at,
            reliability=SOURCE_RELIABILITY["opensky"],
            content=content,
        )
    ]

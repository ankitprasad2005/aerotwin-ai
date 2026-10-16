"""Evidence provider for the airport charges of a route's two airports (AERA tariff orders)."""
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import airport_charges as dataset
from app.datasets.evidence import _twin_route_pairs, parse_route
from app.datasets.queries import latest_snapshot
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.reliability import SOURCE_RELIABILITY
from app.tools import airport_charges_tools as tools

EVIDENCE_SOURCE = "aera"


def _today() -> date:
    return date.today()


def _end(turnaround: dict | None) -> dict | None:
    if turnaround is None:
        return None
    return {
        "airport": turnaround["airport"], "landing_inr": turnaround["landing_inr"], "parking_inr": turnaround["parking_inr"],
        "total_inr": turnaround["total_inr"], "total_usd": turnaround["total_usd"],
    }


async def airport_charges(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """Per route: the turnaround cost (landing + parking/housing) at both airports, the airline charges of one
    flight and its weekly change, and the passenger charges (UDF). The request's route, or every twin route when
    it has none. Routes with no published charge at either end are left out; [] when no charges are stored.
    """
    rows = await dataset.charge_rows(db)
    if not rows:
        return []
    parsed = parse_route(request.route)
    pairs = [parsed] if parsed else await _twin_route_pairs(db)
    snapshot = await latest_snapshot(db, dataset.SOURCE)
    rate, rate_date = await tools._latest_fx(db)
    day = _today()
    items = []
    for origin, destination in pairs:
        entry = tools.route_charges(rows, origin, destination, day, rate, rate_date)
        if entry["origin"] is None and entry["destination"] is None:
            continue
        items.append(
            EvidenceItem(
                id=f"airport:{origin}-{destination}",
                source=EVIDENCE_SOURCE,
                kind="dataset",
                title=f"Airport charges for {origin}-{destination} (AERA tariff orders)",
                url=dataset.SOURCE_URL,
                fetched_at=snapshot.fetched_at if snapshot else None,
                reliability=SOURCE_RELIABILITY[EVIDENCE_SOURCE],
                content={
                    "route": entry["route"],
                    "aircraft_type": tools.ASSUMED_AIRCRAFT_TYPE,
                    "parking_hours": tools.DEFAULT_PARKING_HOURS,
                    "as_of": day.isoformat(),
                    "origin": _end(entry["origin"]),
                    "destination": _end(entry["destination"]),
                    "per_flight_inr": entry["per_flight_inr"],
                    "per_flight_usd": entry["per_flight_usd"],
                    "weekly_change_if_one_weekly_flight_added_inr": entry["weekly_change_if_one_weekly_flight_added_inr"],
                    "weekly_change_if_one_weekly_flight_removed_inr": entry["weekly_change_if_one_weekly_flight_removed_inr"],
                    "passenger_charges": entry["passenger_charges"],
                    "usd_inr": rate,
                    "sources": _dedupe(entry["sources"]),
                    "snapshot_status": snapshot.status if snapshot else None,
                    "snapshot_note": snapshot.error if snapshot else None,
                    "notes": entry["notes"],
                },
            )
        )
    return items


def _dedupe(sources: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for source in sources:
        seen.setdefault((source["source_url"], source["page"]), source)
    return list(seen.values())

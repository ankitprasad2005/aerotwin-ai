"""Deterministic airport-charge arithmetic: what one A320/A321/B737 turnaround costs at an Indian airport.

All rates come from AERA tariff orders (see app/datasets/airport_charges.py) and all aircraft weights from the
manufacturers' airport-planning documents (fallback/aircraft_mtow.csv); nothing here is estimated by an LLM.

Landing charge (per landing): the aircraft's MTOW is rounded to whole tonnes as the airport's order says ("next
rounded off MT" at Delhi and Mumbai, "nearest MT" elsewhere). A flat rate is `rate * tonnes`; the AAI cards of
Chennai and Kolkata use weight slabs, each `base + rate * (tonnes - slab_from)` (the lowest slab is `rate *
tonnes`). A minimum per landing applies where the order sets one (Rs 8,000 at Delhi and Mumbai).

Parking/housing charge (per turnaround): the stand time plus the standard time the order adds (30 minutes at
most airports) less the free period (2 hours) is the chargeable time, rounded to whole hours as the order says.
Each hour is charged at the tier rate for its position after the free period (tiers carry a multiplier at
Delhi); a tier rate is `rate * tonnes` per hour, or `base + rate * (tonnes - slab_from)` per hour for the heavy
slab of the AAI cards. Chennai and Kolkata subsume housing in parking; the other cards list no housing charge.

Passenger charges (user development fee, UDF) are paid by passengers through the fare, not by the airline, and
are reported separately because they affect fare competitiveness. Amounts exclude GST. The aviation security
fee is set by the Ministry of Civil Aviation, is not in the AERA rate cards and is not included.

Money is INR as published; USD uses the latest stored USD/INR rate (INR per USD).
"""
import csv
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import fx
from app.datasets.airport_charges import SOURCE_URL, charge_rows
from app.models.digital_twin import Airport, Route
from app.models.external import AirportCharge, FxRate

MTOW_CSV = Path(__file__).resolve().parent.parent / "datasets" / "fallback" / "aircraft_mtow.csv"
# The twin's aircraft are narrow bodies; Delhi prices narrow and wide bodies differently.
AIRCRAFT_CLASS = "narrow_body"
# query_airport_charges prices every route with this type (the twin's routes carry 180 seats) and stand time.
ASSUMED_AIRCRAFT_TYPE = "A320"
DEFAULT_PARKING_HOURS = 1.0
DEFAULT_STAND = "contact"
PASSENGER_NOTE = "Charged to passengers through the fare, excluding GST; they affect fare competitiveness, not airline cost."


class ChargesUnavailable(ValueError):
    """No published charge is stored for the request: the figure is withheld rather than guessed."""


# ---------------------------------------------------------------- inputs
@lru_cache(maxsize=1)
def _mtow_table() -> dict[str, dict]:
    with MTOW_CSV.open(newline="", encoding="utf-8") as handle:
        return {r["aircraft_type"].upper(): r for r in csv.DictReader(handle)}


def aircraft_reference(aircraft_type: str) -> dict:
    """MTOW and source of an aircraft type (A320, A321, B737) from the manufacturer's airport-planning document."""
    record = _mtow_table().get((aircraft_type or "").strip().upper())
    if record is None:
        raise ChargesUnavailable(f"no published MTOW for aircraft type {aircraft_type!r}; known: {', '.join(_mtow_table())}")
    kg = int(record["mtow_kg"])
    return {
        "aircraft_type": record["aircraft_type"], "variant": record["variant"], "mtow_kg": kg, "mtow_tonnes": kg / 1000,
        "aircraft_class": AIRCRAFT_CLASS, "source_url": record["source_url"], "source_title": record["source_title"],
        "page": record["page"],
    }


def round_mt(tonnes: float, mode: str | None) -> int:
    """Whole tonnes: 'up' = next rounded off MT, anything else = nearest MT (half up)."""
    value = Decimal(str(round(tonnes, 6)))
    return int(value.to_integral_value(rounding=ROUND_CEILING if mode == "up" else ROUND_HALF_UP))


def round_hours(hours: float, mode: str | None) -> int:
    """Whole chargeable hours: 'up' = part of an hour counts as an hour, 'nearest' = half up."""
    value = Decimal(str(round(hours, 6)))
    return int(value.to_integral_value(rounding=ROUND_CEILING if mode == "up" else ROUND_HALF_UP))


def _active(rows: list[AirportCharge], airport: str, charge_type: str, on_date: date, aircraft_class: str | None = None) -> list[AirportCharge]:
    return [
        r for r in rows
        if r.airport == airport.upper() and r.charge_type == charge_type and r.applies_to == "domestic"
        and r.effective_from <= on_date and (r.effective_to is None or on_date <= r.effective_to)
        and (aircraft_class is None or r.aircraft_class in ("all", aircraft_class))
    ]


def _money(value: float) -> float:
    return round(value + 0.0, 2)


def _source(row: AirportCharge) -> dict:
    return {"source_url": row.source_url, "source_title": row.source_title, "page": row.page}


def _sources(rows: list[AirportCharge]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for row in rows:
        seen.setdefault((row.source_url, row.page), _source(row))
    return list(seen.values())


def _slab_row(candidates: list[AirportCharge], weight_mt: float, what: str, airport: str, on_date: date) -> AirportCharge:
    for row in sorted(candidates, key=lambda r: r.slab_from_tonnes):
        if row.slab_from_tonnes < weight_mt and (row.slab_to_tonnes is None or weight_mt <= row.slab_to_tonnes):
            return row
    raise ChargesUnavailable(f"no {what} rate for {weight_mt} t at {airport.upper()} on {on_date.isoformat()}")


def _amount(row: AirportCharge, weight_mt: float) -> float:
    """`rate * tonnes`, or `base + rate * (tonnes - slab_from)` for a slab that has a base."""
    if row.base_inr is None:
        return row.rate_inr * weight_mt
    return row.base_inr + row.rate_inr * (weight_mt - row.slab_from_tonnes)


# ---------------------------------------------------------------- landing
def landing_charge(rows: list[AirportCharge], airport: str, weight_tonnes: float, aircraft_class: str, on_date: date) -> dict:
    """The landing charge in INR of one landing of an aircraft of `weight_tonnes` MTOW. Raises ChargesUnavailable."""
    candidates = _active(rows, airport, "landing", on_date, aircraft_class)
    if not candidates:
        raise ChargesUnavailable(f"no landing charge is stored for {airport.upper()} on {on_date.isoformat()}")
    weight = round_mt(weight_tonnes, candidates[0].mt_rounding)
    row = _slab_row(candidates, weight, "landing", airport, on_date)
    charge = _amount(row, weight)
    used = [row]
    minimum_applied = False
    minimums = _active(rows, airport, "landing_minimum", on_date)
    if minimums and charge < minimums[0].rate_inr:
        charge, minimum_applied = minimums[0].rate_inr, True
        used.append(minimums[0])
    return {
        "charge_inr": _money(charge), "weight_mt": weight, "rate_inr": row.rate_inr, "slab_base_inr": row.base_inr,
        "slab_from_tonnes": row.slab_from_tonnes, "minimum_applied": minimum_applied, "effective_from": row.effective_from.isoformat(),
        "sources": _sources(used),
    }


# ---------------------------------------------------------------- parking / housing
def parking_charge(
    rows: list[AirportCharge], airport: str, weight_tonnes: float, parking_hours: float, aircraft_class: str,
    on_date: date, stand_type: str = DEFAULT_STAND,
) -> dict:
    """The parking (and housing) charge in INR for `parking_hours` on the stand. Raises ChargesUnavailable."""
    if parking_hours < 0:
        raise ValueError("parking_hours must not be negative")
    candidates = [
        r for r in _active(rows, airport, "parking", on_date, aircraft_class) if r.stand_type in ("all", stand_type)
    ]
    if not candidates:
        raise ChargesUnavailable(f"no parking charge is stored for {airport.upper()} ({stand_type} stand) on {on_date.isoformat()}")
    first = candidates[0]
    weight = round_mt(weight_tonnes, first.mt_rounding)
    free, added = first.free_hours or 0.0, first.standard_added_hours or 0.0
    chargeable = round_hours(max(0.0, parking_hours + added - free), first.hour_rounding)

    tiers, total, used = [], 0.0, []
    for hour_from in sorted({r.hour_from for r in candidates}):
        tier_rows = [r for r in candidates if r.hour_from == hour_from]
        row = _slab_row(tier_rows, weight, "parking", airport, on_date)
        hour_to = row.hour_to
        hours = max(0.0, min(chargeable, hour_to if hour_to is not None else chargeable) - hour_from)
        per_hour = _amount(row, weight) * row.rate_multiplier
        total += hours * per_hour
        tiers.append({"hour_from": hour_from, "hour_to": hour_to, "hours": hours, "rate_per_hour_inr": _money(per_hour)})
        if hours:
            used.append(row)
    return {
        "charge_inr": _money(total), "stand_type": stand_type, "weight_mt": weight, "parking_hours": parking_hours,
        "free_hours": free, "standard_added_hours": added, "chargeable_hours": chargeable, "tiers": tiers,
        "effective_from": first.effective_from.isoformat(), "sources": _sources(used or [first]),
    }


def _housing_note(rows: list[AirportCharge], airport: str, on_date: date) -> str:
    parking = _active(rows, airport, "parking", on_date)
    if any("housing charges are subsumed" in (r.notes or "") for r in parking):
        return f"At {airport.upper()} housing charges are subsumed within the parking charges (AERA order)."
    return f"The AERA rate card of {airport.upper()} lists no separate housing charge; parking is the only stand-related charge."


# ---------------------------------------------------------------- one turnaround
def _usd(inr: float, usd_inr: float | None) -> float | None:
    return None if not usd_inr else _money(inr / usd_inr)


def compute_turnaround(
    rows: list[AirportCharge], airport: str, aircraft_type: str, parking_hours: float, on_date: date,
    usd_inr: float | None, stand_type: str = DEFAULT_STAND, usd_inr_date: str | None = None,
) -> dict:
    """Landing + parking/housing of one turnaround, in INR and USD. Pure: callers load `rows` and the FX rate."""
    aircraft = aircraft_reference(aircraft_type)
    landing = landing_charge(rows, airport, aircraft["mtow_tonnes"], aircraft["aircraft_class"], on_date)
    parking = parking_charge(rows, airport, aircraft["mtow_tonnes"], parking_hours, aircraft["aircraft_class"], on_date, stand_type)
    total = landing["charge_inr"] + parking["charge_inr"]
    notes = [
        "Landing and parking per AERA tariff order, excluding GST. MTOW is the manufacturer's published figure; "
        "an airline's certificate of airworthiness may state a different weight.",
        _housing_note(rows, airport, on_date),
    ]
    if not usd_inr:
        notes.append("No USD/INR exchange rate is stored: the USD amounts are unavailable.")
    return {
        "airport": airport.upper(), "aircraft_type": aircraft["aircraft_type"], "mtow_tonnes": aircraft["mtow_tonnes"],
        "mtow_source": {k: aircraft[k] for k in ("source_url", "source_title", "page", "variant")},
        "on_date": on_date.isoformat(), "parking_hours": parking_hours, "stand_type": stand_type,
        "landing": landing, "parking_and_housing": parking,
        "landing_inr": landing["charge_inr"], "parking_inr": parking["charge_inr"], "total_inr": _money(total),
        "usd_inr": usd_inr, "usd_inr_date": usd_inr_date,
        "landing_usd": _usd(landing["charge_inr"], usd_inr), "parking_usd": _usd(parking["charge_inr"], usd_inr),
        "total_usd": _usd(total, usd_inr),
        "effective_from": max(landing["effective_from"], parking["effective_from"]),
        "sources": _sources_union(landing["sources"], parking["sources"]), "notes": notes,
    }


def _sources_union(*groups: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for group in groups:
        for source in group:
            seen.setdefault((source["source_url"], source["page"]), source)
    return list(seen.values())


# ---------------------------------------------------------------- passengers
def compute_passenger_charges(rows: list[AirportCharge], airport: str, on_date: date) -> dict:
    """UDF per embarking and disembarking domestic passenger (None where the order sets no such fee)."""
    embarking = _active(rows, airport, "udf_embarking", on_date)
    disembarking = _active(rows, airport, "udf_disembarking", on_date)
    if not embarking and not disembarking:
        raise ChargesUnavailable(f"no passenger charge is stored for {airport.upper()} on {on_date.isoformat()}")
    used = [*embarking[:1], *disembarking[:1]]
    notes = [
        PASSENGER_NOTE,
        "The aviation security fee is set by the Ministry of Civil Aviation, is not in the AERA rate card and is not included.",
    ]
    if not disembarking:
        notes.append(f"The AERA order for {airport.upper()} sets a departing-passenger UDF only; there is no disembarking UDF.")
    return {
        "airport": airport.upper(), "on_date": on_date.isoformat(), "paid_by": "passengers",
        "embarking_inr": embarking[0].rate_inr if embarking else None,
        "disembarking_inr": disembarking[0].rate_inr if disembarking else None,
        "effective_from": max(r.effective_from for r in used).isoformat(), "sources": _sources(used), "notes": notes,
    }


# ---------------------------------------------------------------- database-backed
async def _latest_fx(db: AsyncSession) -> tuple[float | None, str | None]:
    row = (
        await db.execute(
            select(FxRate).where(FxRate.base == fx.BASE, FxRate.quote == fx.QUOTE).order_by(FxRate.rate_date.desc()).limit(1)
        )
    ).scalars().first()
    return (row.rate, row.rate_date.isoformat()) if row else (None, None)


async def turnaround_charges(
    db: AsyncSession, airport: str, aircraft_type: str, parking_hours: float = DEFAULT_PARKING_HOURS, *,
    on_date: date | None = None, stand_type: str = DEFAULT_STAND,
) -> dict:
    """Landing + parking/housing of one turnaround of `aircraft_type` at `airport`, in INR and USD (latest stored rate)."""
    rows = await charge_rows(db, airport)
    rate, rate_date = await _latest_fx(db)
    return compute_turnaround(
        rows, airport, aircraft_type, parking_hours, on_date or date.today(), rate, stand_type, rate_date
    )


async def passenger_charges(db: AsyncSession, airport: str, *, on_date: date | None = None) -> dict:
    """The passenger charges (UDF) at `airport`, shown apart from airline cost."""
    return compute_passenger_charges(await charge_rows(db, airport), airport, on_date or date.today())


async def _twin_routes(db: AsyncSession) -> list[tuple[str, str]]:
    origin, destination = Airport.__table__.alias("o"), Airport.__table__.alias("d")
    stmt = (
        select(origin.c.code, destination.c.code)
        .select_from(Route.__table__.join(origin, Route.origin_id == origin.c.id).join(destination, Route.destination_id == destination.c.id))
        .order_by(origin.c.code, destination.c.code)
    )
    return [(o, d) for o, d in (await db.execute(stmt)).all()]


def _try(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except ChargesUnavailable as exc:
        return None, str(exc)


def _passenger_block(origin: dict | None, destination: dict | None) -> dict:
    embarking = origin["embarking_inr"] if origin else None
    disembarking = destination["disembarking_inr"] if destination else None
    known = [v for v in (embarking, disembarking) if v is not None]
    return {
        "origin_embarking_inr": embarking, "destination_disembarking_inr": disembarking,
        "per_passenger_inr": _money(sum(known)) if known else None, "paid_by": "passengers", "note": PASSENGER_NOTE,
    }


def route_charges(
    rows: list[AirportCharge], origin_code: str, destination_code: str, day: date, rate: float | None,
    rate_date: str | None, aircraft_type: str = ASSUMED_AIRCRAFT_TYPE, parking_hours: float = DEFAULT_PARKING_HOURS,
) -> dict:
    """The airport charges of one flight on origin-destination (see query_airport_charges); `sources` lists the documents used."""
    route_notes, sources = [], []
    ends, passengers = {}, {}
    for key, code in (("origin", origin_code), ("destination", destination_code)):
        turnaround, why = _try(compute_turnaround, rows, code, aircraft_type, parking_hours, day, rate, DEFAULT_STAND, rate_date)
        pax, _ = _try(compute_passenger_charges, rows, code, day)
        ends[key], passengers[key] = turnaround, pax
        if why:
            route_notes.append(f"{code}: {why}")
        sources += (turnaround["sources"] if turnaround else []) + (pax["sources"] if pax else [])
    origin_end, destination_end = ends["origin"], ends["destination"]
    per_flight = _money(destination_end["landing_inr"] + origin_end["parking_inr"]) if origin_end and destination_end else None
    per_flight_usd = _usd(per_flight, rate) if per_flight is not None else None
    return {
        "route": f"{origin_code.upper()}-{destination_code.upper()}",
        "origin": origin_end,
        "destination": destination_end,
        "per_flight_inr": per_flight,
        "per_flight_usd": per_flight_usd,
        "weekly_change_if_one_weekly_flight_added_inr": per_flight,
        "weekly_change_if_one_weekly_flight_removed_inr": -per_flight if per_flight is not None else None,
        "weekly_change_if_one_weekly_flight_added_usd": per_flight_usd,
        "weekly_change_if_one_weekly_flight_removed_usd": -per_flight_usd if per_flight_usd is not None else None,
        "passenger_charges": _passenger_block(passengers["origin"], passengers["destination"]),
        "notes": route_notes,
        "sources": sources,
    }


async def query_airport_charges(db: AsyncSession, *, on_date: date | None = None) -> dict:
    """Airport charges of every twin route, for an A320 with a 1 hour stand time.

    Per route: the turnaround charges (landing + parking/housing) at the origin and at the destination; the
    airline charges of ONE flight, `per_flight_*` = the landing at the destination plus the parking at the origin
    (the landing at the origin belongs to the inbound flight of the paired return route); the weekly airport-charge
    change if one weekly flight is added (+per flight) or removed (-per flight); and the passenger charges (UDF
    embarking at the origin, disembarking at the destination), which passengers pay and which are not airline cost.
    Anything the AERA orders do not give is null with a note, never estimated.
    """
    day = on_date or date.today()
    rows = await charge_rows(db)
    rate, rate_date = await _latest_fx(db)
    notes = [
        "Charges are per AERA tariff orders (curated, see sources), excluding GST; the aircraft type and stand time "
        f"are assumptions: {ASSUMED_AIRCRAFT_TYPE}, {DEFAULT_PARKING_HOURS:g} hour on a {DEFAULT_STAND} stand.",
    ]
    if not rows:
        notes.append("No airport charges are loaded (run the airport_charges dataset refresh): every figure is null.")
    if rate is None:
        notes.append("No USD/INR exchange rate is stored: USD amounts are null.")

    sources: dict[tuple, dict] = {}
    routes = []
    for origin_code, destination_code in await _twin_routes(db):
        entry = route_charges(rows, origin_code, destination_code, day, rate, rate_date)
        for source in entry.pop("sources"):
            sources.setdefault((source["source_url"], source["page"]), source)
        routes.append(entry)
    return {
        "airport_charges": {
            "as_of": day.isoformat(), "aircraft_type": ASSUMED_AIRCRAFT_TYPE, "parking_hours": DEFAULT_PARKING_HOURS,
            "stand_type": DEFAULT_STAND, "usd_inr": rate, "usd_inr_date": rate_date, "routes": routes,
            "sources": list(sources.values()) or [{"source_url": SOURCE_URL, "source_title": "AERA tariff orders", "page": None}],
            "notes": notes,
        }
    }

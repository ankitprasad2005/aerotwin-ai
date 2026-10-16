"""Exact tests of the airport-charge arithmetic. Every expected number is computed by hand in the comment above it,
from the rate cards stored in app/datasets/fallback/airport_charges.csv (AERA tariff orders) and the aircraft
weights in aircraft_mtow.csv (A320 78 t, A321 93.5 t, B737-800 79.015 t)."""
from datetime import date

import pytest

from app.datasets import airport_charges as dataset
from app.models.external import AirportCharge, FxRate
from app.seed.seed import run_seed
from app.tools import airport_charges_tools as tools

DAY = date(2026, 10, 16)


@pytest.fixture(scope="module")
def rows() -> list[AirportCharge]:
    return [AirportCharge(**row) for row in dataset.load_curated()]


def test_aircraft_reference_weights_come_from_the_manufacturer_documents():
    a320 = tools.aircraft_reference("a320")
    assert (a320["mtow_kg"], a320["mtow_tonnes"], a320["aircraft_class"]) == (78000, 78.0, "narrow_body")
    assert a320["source_url"].endswith("AC_A320_0624.pdf") and a320["page"] == "34"
    assert tools.aircraft_reference("A321")["mtow_tonnes"] == 93.5
    assert tools.aircraft_reference("B737")["mtow_kg"] == 79015
    with pytest.raises(tools.ChargesUnavailable, match="A380"):
        tools.aircraft_reference("A380")


def test_rounding_helpers():
    assert tools.round_mt(93.5, "up") == 94 and tools.round_mt(78.0, "up") == 78 and tools.round_mt(79.015, "up") == 80
    assert tools.round_mt(93.5, "nearest") == 94 and tools.round_mt(93.4, "nearest") == 93 and tools.round_mt(79.015, "nearest") == 79
    assert tools.round_hours(2.5, "nearest") == 3 and tools.round_hours(2.4, "nearest") == 2
    assert tools.round_hours(2.01, "up") == 3 and tools.round_hours(2.0, "up") == 2 and tools.round_hours(0, "up") == 0


# ---------------------------------------------------------------- landing
@pytest.mark.parametrize(
    "airport, weight, expected",
    [
        ("BOM", 78.0, 31356.0),    # 402 * 78
        ("DEL", 78.0, 27066.0),    # 347 (narrow body) * 78
        ("BLR", 78.0, 34476.0),    # 442 * 78
        ("HYD", 78.0, 33930.0),    # 435 * 78
        ("MAA", 78.0, 6404.0),     # slab above 50 MT: 3,800 + 93 * (78 - 50) = 3,800 + 2,604
        ("CCU", 78.0, 43024.0),    # slab above 50 MT: 25,300 + 633 * 28 = 25,300 + 17,724
        ("BOM", 93.5, 37788.0),    # next rounded MT: 94 * 402
        ("BLR", 93.5, 41548.0),    # nearest MT (half up): 94 * 442
        ("DEL", 79.015, 27760.0),  # next rounded MT: 80 * 347
        ("MAA", 79.015, 6497.0),   # nearest MT 79: 3,800 + 93 * 29
        ("MAA", 20.0, 1400.0),     # up to 25 MT is charged on the whole weight: 70 * 20
        ("MAA", 130.0, 11600.0),   # 100-200 MT slab: 8,450 + 105 * 30 = 8,450 + 3,150
        ("CCU", 250.0, 170950.0),  # above 200 MT: 129,150 + 836 * 50 = 129,150 + 41,800
    ],
)
def test_landing_charge(rows, airport, weight, expected):
    assert tools.landing_charge(rows, airport, weight, "narrow_body", DAY)["charge_inr"] == pytest.approx(expected)


def test_landing_minimum_applies_to_light_aircraft(rows):
    # DEL: 347 * 20 = 6,940, below the Rs 8,000 minimum
    result = tools.landing_charge(rows, "DEL", 20.0, "narrow_body", DAY)
    assert result["charge_inr"] == 8000.0 and result["minimum_applied"] is True
    assert tools.landing_charge(rows, "DEL", 78.0, "narrow_body", DAY)["minimum_applied"] is False


def test_wide_body_landing_rate_at_delhi(rows):
    # 564 * 250 (a 250 t wide body)
    assert tools.landing_charge(rows, "DEL", 250.0, "wide_body", DAY)["charge_inr"] == 141000.0


def test_landing_rate_follows_the_effective_date(rows):
    assert tools.landing_charge(rows, "BLR", 78.0, "narrow_body", date(2030, 5, 15))["charge_inr"] == 23010.0  # 295 * 78
    assert tools.landing_charge(rows, "HYD", 78.0, "narrow_body", date(2029, 12, 1))["charge_inr"] == 17940.0  # 230 * 78


def test_landing_without_a_published_rate_is_an_error_not_a_guess(rows):
    with pytest.raises(tools.ChargesUnavailable, match="BLR"):
        tools.landing_charge(rows, "BLR", 78.0, "narrow_body", date(2026, 8, 31))  # BLR's new card starts 2026-09-01
    with pytest.raises(tools.ChargesUnavailable, match="XYZ"):
        tools.landing_charge(rows, "XYZ", 78.0, "narrow_body", DAY)


# ---------------------------------------------------------------- parking / housing
@pytest.mark.parametrize(
    "airport, hours, stand, expected_hours, expected",
    [
        ("BOM", 1.0, "contact", 0, 0.0),          # inside the 2 free hours
        ("BOM", 2.0, "contact", 0, 0.0),
        ("BOM", 4.0, "contact", 2, 4212.0),       # (4 - 2) h * 27 * 78
        ("BOM", 4.0, "remote", 2, 2106.0),        # (4 - 2) h * 13.5 * 78
        ("BOM", 4.1, "contact", 3, 6318.0),       # part of an hour rounds up: 3 h * 27 * 78
        ("DEL", 2.0, "contact", 1, 2808.0),       # +0.5 h standard time: 2.5 - 2 = 0.5 -> 1 h * 36 * 78
        ("DEL", 4.0, "contact", 3, 8424.0),       # 4.5 - 2 = 2.5 -> 3 h * 36 * 78
        ("DEL", 6.0, "contact", 5, 16848.0),      # 6.5 - 2 = 4.5 -> 5 h: 4 h * 36 * 78 + 1 h * 2 * 36 * 78 = 11,232 + 5,616
        ("DEL", 6.0, "remote", 5, 8424.0),        # half the contact rate: 5,616 + 2,808
        ("BLR", 5.0, "contact", 4, 7332.0),       # 5.5 - 2 = 3.5 -> 4 h: 2 h * 18 * 78 + 2 h * 29 * 78 = 2,808 + 4,524
        ("HYD", 3.0, "contact", 2, 5304.0),       # 3.5 - 2 = 1.5 -> 2 h * 34 * 78
        ("HYD", 3.0, "remote", 2, 2652.0),        # 2 h * 17 * 78
        ("MAA", 4.0, "contact", 3, 873.6),        # 4.5 - 2 = 2.5 -> nearest 3 h: 2 h * 2.8 * 78 + 1 h * 5.6 * 78 = 436.8 + 436.8
        ("CCU", 4.0, "contact", 3, 4898.4),       # 3 h: 2 h * 15.7 * 78 + 1 h * 31.4 * 78 = 2,449.2 + 2,449.2
    ],
)
def test_parking_charge(rows, airport, hours, stand, expected_hours, expected):
    result = tools.parking_charge(rows, airport, 78.0, hours, "narrow_body", DAY, stand)
    assert result["chargeable_hours"] == expected_hours
    assert result["charge_inr"] == pytest.approx(expected)


def test_parking_above_100_tonnes_uses_the_base_plus_excess_rate(rows):
    # MAA, 130 t, 3 chargeable hours (4 h stand time): first tier 2 h * (280 + 3.7 * 30) = 2 * 391 = 782,
    # beyond four hours 1 h * (560 + 7.5 * 30) = 785 -> 1,567
    result = tools.parking_charge(rows, "MAA", 130.0, 4.0, "wide_body", DAY, "contact")
    assert result["charge_inr"] == pytest.approx(1567.0)


def test_parking_breakdown_lists_the_tiers(rows):
    result = tools.parking_charge(rows, "DEL", 78.0, 6.0, "narrow_body", DAY, "contact")
    assert [(t["hour_from"], t["hours"], t["rate_per_hour_inr"]) for t in result["tiers"] if t["hours"]] == [
        (0, 4, 2808.0), (4, 1, 5616.0),
    ]
    assert (result["free_hours"], result["standard_added_hours"], result["weight_mt"]) == (2.0, 0.5, 78)


def test_a_weight_outside_every_slab_and_an_unknown_airport_are_errors(rows):
    with pytest.raises(tools.ChargesUnavailable, match="no landing rate for 0"):
        tools.landing_charge(rows, "MAA", 0.0, "narrow_body", DAY)
    with pytest.raises(tools.ChargesUnavailable, match="no parking charge"):
        tools.parking_charge(rows, "XYZ", 78.0, 3.0, "narrow_body", DAY)
    with pytest.raises(tools.ChargesUnavailable, match="remote"):
        tools.parking_charge([r for r in rows if r.stand_type != "remote"], "HYD", 78.0, 3.0, "narrow_body", DAY, "remote")


def test_parking_rejects_negative_hours(rows):
    with pytest.raises(ValueError):
        tools.parking_charge(rows, "BOM", 78.0, -1, "narrow_body", DAY)


# ---------------------------------------------------------------- one turnaround
def test_turnaround_at_mumbai_and_delhi_for_an_a320_with_a_usd_conversion(rows):
    bom = tools.compute_turnaround(rows, "BOM", "A320", 4.0, DAY, usd_inr=85.0)
    # landing 402 * 78 = 31,356; parking 2 h * 27 * 78 = 4,212; total 35,568 INR = 418.45 USD at 85 INR/USD
    assert (bom["landing_inr"], bom["parking_inr"], bom["total_inr"]) == (31356.0, 4212.0, 35568.0)
    assert (bom["landing_usd"], bom["parking_usd"], bom["total_usd"]) == (368.89, 49.55, 418.45)
    assert bom["mtow_tonnes"] == 78.0 and bom["usd_inr"] == 85.0 and bom["effective_from"] == "2025-05-16"
    assert bom["sources"][0]["source_url"].endswith("17466350622028.pdf")

    delhi = tools.compute_turnaround(rows, "DEL", "A320", 4.0, DAY, usd_inr=85.0)
    # landing 347 * 78 = 27,066; parking 3 h * 36 * 78 = 8,424; total 35,490 INR = 417.53 USD
    assert (delhi["landing_inr"], delhi["parking_inr"], delhi["total_inr"]) == (27066.0, 8424.0, 35490.0)
    assert delhi["total_usd"] == 417.53


def test_turnaround_without_an_fx_rate_has_no_usd(rows):
    result = tools.compute_turnaround(rows, "BOM", "A320", 1.0, DAY, usd_inr=None)
    assert result["total_inr"] == 31356.0 and result["total_usd"] is None and result["usd_inr"] is None
    assert any("USD/INR" in note for note in result["notes"])


def test_turnaround_notes_say_housing_is_subsumed_where_the_order_says_so(rows):
    chennai = tools.compute_turnaround(rows, "MAA", "A320", 1.0, DAY, usd_inr=85.0)
    assert any("housing" in note.lower() and "subsumed" in note.lower() for note in chennai["notes"])
    mumbai = tools.compute_turnaround(rows, "BOM", "A320", 1.0, DAY, usd_inr=85.0)
    assert any("no separate housing" in note.lower() for note in mumbai["notes"])


# ---------------------------------------------------------------- passengers
@pytest.mark.parametrize(
    "airport, day, embarking, disembarking",
    [
        ("BOM", DAY, 175.0, 75.0),
        ("DEL", DAY, 129.0, 56.0),
        ("BLR", DAY, 300.0, 125.0),
        ("HYD", DAY, 515.0, 220.0),
        ("HYD", date(2029, 12, 1), 415.0, 175.0),
        ("MAA", DAY, 410.0, None),   # Chennai's order sets a departing-passenger UDF only
        ("CCU", DAY, 547.0, None),
    ],
)
def test_passenger_charges(rows, airport, day, embarking, disembarking):
    result = tools.compute_passenger_charges(rows, airport, day)
    assert (result["embarking_inr"], result["disembarking_inr"]) == (embarking, disembarking)
    assert result["paid_by"] == "passengers" and result["sources"]
    assert any("security fee" in n.lower() for n in result["notes"])


def test_passenger_charges_unavailable_for_an_unknown_airport(rows):
    with pytest.raises(tools.ChargesUnavailable):
        tools.compute_passenger_charges(rows, "XYZ", DAY)


# ---------------------------------------------------------------- database-backed
async def _load(db, usd_inr: float | None = 85.0):
    await dataset.fetch_airport_charges(db)
    if usd_inr is not None:
        db.add(FxRate(base="USD", quote="INR", rate_date=date(2026, 10, 15), rate=usd_inr - 1))
        db.add(FxRate(base="USD", quote="INR", rate_date=date(2026, 10, 16), rate=usd_inr))
    await db.flush()


async def test_turnaround_charges_uses_the_latest_stored_rate(db_session):
    await _load(db_session)
    result = await tools.turnaround_charges(db_session, "bom", "A320", 4.0, on_date=DAY)
    assert result["total_inr"] == 35568.0 and result["total_usd"] == 418.45
    assert result["usd_inr_date"] == "2026-10-16"  # the latest of the two stored rates (85, not 84)


async def test_turnaround_charges_without_stored_charges_raises(db_session):
    with pytest.raises(tools.ChargesUnavailable):
        await tools.turnaround_charges(db_session, "BOM", "A320", 1.0, on_date=DAY)


async def test_passenger_charges_from_the_database(db_session):
    await _load(db_session)
    result = await tools.passenger_charges(db_session, "BOM", on_date=DAY)
    assert (result["embarking_inr"], result["disembarking_inr"]) == (175.0, 75.0)


async def test_query_airport_charges_for_every_twin_route(db_session):
    await run_seed(db_session)
    await _load(db_session)

    data = (await tools.query_airport_charges(db_session, on_date=DAY))["airport_charges"]

    assert data["aircraft_type"] == "A320" and data["parking_hours"] == 1.0
    assert data["usd_inr"] == 85.0 and data["usd_inr_date"] == "2026-10-16"
    by_route = {r["route"]: r for r in data["routes"]}
    assert set(by_route) == {"BOM-DEL", "DEL-BOM", "BOM-BLR", "BLR-HYD", "MAA-CCU"}

    # BOM-DEL: the flight lands at DEL (347 * 78 = 27,066) and its 1 h turnaround stand time at BOM is inside the free period
    bom_del = by_route["BOM-DEL"]
    assert bom_del["origin"]["airport"] == "BOM" and bom_del["destination"]["airport"] == "DEL"
    assert bom_del["origin"]["landing_inr"] == 31356.0 and bom_del["destination"]["landing_inr"] == 27066.0
    assert bom_del["per_flight_inr"] == 27066.0 and bom_del["per_flight_usd"] == 318.42
    assert bom_del["weekly_change_if_one_weekly_flight_added_inr"] == 27066.0
    assert bom_del["weekly_change_if_one_weekly_flight_removed_inr"] == -27066.0
    assert bom_del["weekly_change_if_one_weekly_flight_added_usd"] == 318.42
    # passengers pay UDF 175 embarking at BOM and 56 disembarking at DEL
    assert bom_del["passenger_charges"] == {
        "origin_embarking_inr": 175.0, "destination_disembarking_inr": 56.0, "per_passenger_inr": 231.0,
        "paid_by": "passengers",
        "note": "Charged to passengers through the fare, excluding GST; they affect fare competitiveness, not airline cost.",
    }
    assert by_route["DEL-BOM"]["per_flight_inr"] == 31356.0                 # lands at BOM: 402 * 78
    assert by_route["BOM-BLR"]["per_flight_inr"] == 34476.0                 # lands at BLR: 442 * 78
    assert by_route["BLR-HYD"]["per_flight_inr"] == 33930.0                 # lands at HYD: 435 * 78
    assert by_route["BLR-HYD"]["passenger_charges"]["per_passenger_inr"] == 520.0  # 300 + 220
    maa_ccu = by_route["MAA-CCU"]
    assert maa_ccu["per_flight_inr"] == 43024.0                             # lands at CCU: 25,300 + 633 * 28
    assert maa_ccu["passenger_charges"]["destination_disembarking_inr"] is None
    assert maa_ccu["passenger_charges"]["per_passenger_inr"] == 410.0       # only the departing UDF is published
    assert data["sources"] and data["notes"]


async def test_query_airport_charges_without_data_returns_nulls_and_a_note(db_session):
    await run_seed(db_session)

    data = (await tools.query_airport_charges(db_session, on_date=DAY))["airport_charges"]

    assert data["usd_inr"] is None
    assert all(r["per_flight_inr"] is None and r["origin"] is None for r in data["routes"])
    assert any("No airport charges" in note for note in data["notes"])


async def test_query_airport_charges_without_fx_has_inr_only(db_session):
    await run_seed(db_session)
    await _load(db_session, usd_inr=None)

    data = (await tools.query_airport_charges(db_session, on_date=DAY))["airport_charges"]

    route = next(r for r in data["routes"] if r["route"] == "BOM-DEL")
    assert route["per_flight_inr"] == 27066.0 and route["per_flight_usd"] is None
    assert any("USD/INR" in note for note in data["notes"])


async def test_query_airport_charges_marks_a_route_end_without_charges(db_session):
    await run_seed(db_session)
    await _load(db_session)
    from sqlalchemy import delete

    await db_session.execute(delete(AirportCharge).where(AirportCharge.airport == "DEL"))
    data = (await tools.query_airport_charges(db_session, on_date=DAY))["airport_charges"]

    bom_del = next(r for r in data["routes"] if r["route"] == "BOM-DEL")
    assert bom_del["destination"] is None and bom_del["per_flight_inr"] is None
    assert bom_del["origin"]["airport"] == "BOM"
    assert bom_del["passenger_charges"]["destination_disembarking_inr"] is None
    assert any("DEL" in note for note in bom_del["notes"])
    del_bom = next(r for r in data["routes"] if r["route"] == "DEL-BOM")
    assert del_bom["per_flight_inr"] is None and del_bom["origin"] is None  # both ends are needed: nothing is guessed

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.datasets import opensky_live
from app.datasets.air_traffic import (
    AIRPORTS_BY_IATA, APPROACH_RADIUS_KM, HUBS, INDIA_AIRPORTS, StateVector, air_traffic_history, assign_to_airports,
    fixed_congestion, haversine_km, latest_air_traffic, live_congestion, nearest_airport, totals,
)
from app.models.external import AirportTrafficLive, AirTrafficSnapshot

FIXTURE = Path(__file__).parent / "fixtures" / "datasets" / "opensky_states_india.json"
T0 = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def test_airport_list_covers_the_twin_and_the_top_25():
    assert len(INDIA_AIRPORTS) >= 25
    assert {a.iata for a in INDIA_AIRPORTS[:6]} == HUBS == {"BOM", "DEL", "BLR", "MAA", "HYD", "CCU"}
    assert all(len(a.icao) == 4 and a.icao.startswith(("V",)) for a in INDIA_AIRPORTS)
    assert len(AIRPORTS_BY_IATA) == len(INDIA_AIRPORTS)


def test_haversine_known_distances():
    bom, delhi = AIRPORTS_BY_IATA["BOM"], AIRPORTS_BY_IATA["DEL"]
    assert haversine_km(bom.lat, bom.lon, bom.lat, bom.lon) == 0
    assert haversine_km(bom.lat, bom.lon, delhi.lat, delhi.lon) == pytest.approx(1136, abs=15)


def test_nearest_airport_and_distance():
    delhi = AIRPORTS_BY_IATA["DEL"]
    airport, dist = nearest_airport(delhi.lat + 0.1, delhi.lon)
    assert airport.iata == "DEL" and dist == pytest.approx(11.1, abs=0.2)


def _v(airport: str, dlat: float, on_ground: bool, key: str = "x") -> StateVector:
    a = AIRPORTS_BY_IATA[airport]
    return StateVector(icao24=key, callsign=None, lat=a.lat + dlat, lon=a.lon, on_ground=on_ground)


def test_assignment_uses_radii_and_ground_state():
    vectors = [
        _v("BOM", 0.0, True),  # at the airport, on the ground
        _v("BOM", 0.15, True),  # ~17 km, on the ground: inside 25 km
        _v("BOM", 0.3, True),  # ~33 km on the ground: outside the terminal radius, not counted
        _v("BOM", 0.5, False),  # ~55 km airborne: approach airspace
        _v("BOM", 0.9, False),  # ~100 km airborne: outside 80 km
        _v("DEL", 0.0, False),
    ]
    counts = assign_to_airports(vectors)
    assert counts["BOM"] == {"on_ground_nearby": 2, "airborne_nearby": 1, "aircraft_within_radius": 3}
    assert counts["DEL"]["aircraft_within_radius"] == 1
    assert counts["BLR"]["aircraft_within_radius"] == 0  # zeros are kept
    assert set(counts) == {a.iata for a in INDIA_AIRPORTS}
    assert totals(vectors) == {"aircraft_over_india": 6, "airborne": 3, "on_ground": 3}
    assert APPROACH_RADIUS_KM == 80


def test_aircraft_goes_to_the_nearer_of_two_airports():
    # Between Chennai and Bengaluru-ish: pick a point 10 km from MAA.
    counts = assign_to_airports([_v("MAA", 0.09, False)])
    assert counts["MAA"]["airborne_nearby"] == 1 and sum(c["aircraft_within_radius"] for c in counts.values()) == 1


@pytest.mark.parametrize(
    "iata,count,expected",
    [("DEL", 7, "LOW"), ("DEL", 8, "MODERATE"), ("DEL", 19, "MODERATE"), ("DEL", 20, "HIGH"),
     ("JAI", 2, "LOW"), ("JAI", 3, "MODERATE"), ("JAI", 7, "MODERATE"), ("JAI", 8, "HIGH")],
)
def test_fixed_thresholds(iata, count, expected):
    assert fixed_congestion(iata, count) == expected


def test_congestion_uses_fixed_thresholds_with_too_little_history():
    assert live_congestion("DEL", 25, [10, 10, 10, 10, 10]) == ("HIGH", None)  # 5 < MIN_HISTORY


def test_congestion_relative_to_median_history():
    history = [10, 12, 8, 10, 11, 9, 10, 10]  # median 10
    assert live_congestion("DEL", 7, history) == ("LOW", 10.0)
    assert live_congestion("DEL", 8, history) == ("MODERATE", 10.0)
    assert live_congestion("DEL", 12, history) == ("MODERATE", 10.0)
    assert live_congestion("DEL", 13, history) == ("HIGH", 10.0)


def test_congestion_only_looks_at_the_last_twelve_and_falls_back_on_a_tiny_baseline():
    assert live_congestion("DEL", 6, [4] * 12 + [100] * 30) == ("HIGH", 4.0)
    assert live_congestion("JAI", 9, [0, 1, 0, 0, 1, 0, 0]) == ("HIGH", None)  # median 0 < MIN_BASELINE


def test_real_fixture_assignment():
    payload = json.loads(FIXTURE.read_bytes())
    taken_at, vectors = opensky_live.parse_states(FIXTURE.read_bytes())
    assert taken_at == datetime.fromtimestamp(payload["time"], tz=timezone.utc)
    counts = assign_to_airports(vectors)
    assert counts["DEL"]["aircraft_within_radius"] >= 10
    assert sum(c["aircraft_within_radius"] for c in counts.values()) <= len(vectors)


async def _store(db, minutes_ago: int, counts: dict[str, int], total: int = 100, arrivals=None):
    taken = T0 - timedelta(minutes=minutes_ago)
    db.add(AirTrafficSnapshot(taken_at=taken, aircraft_over_india=total, airborne=total - 5, on_ground=5))
    for iata, n in counts.items():
        a = AIRPORTS_BY_IATA[iata]
        db.add(AirportTrafficLive(
            taken_at=taken, airport=iata, icao=a.icao, aircraft_within_radius=n, on_ground_nearby=n // 2,
            airborne_nearby=n - n // 2, arrivals_last_24h=arrivals, departures_last_24h=arrivals,
        ))
    await db.flush()


async def test_latest_air_traffic_empty(db_session):
    assert await latest_air_traffic(db_session) is None


async def test_latest_air_traffic_with_history_and_filter(db_session):
    for i in range(1, 9):  # eight earlier snapshots, DEL median 10
        await _store(db_session, i * 10, {"DEL": 10, "BOM": 4})
    await _store(db_session, 0, {"DEL": 14, "BOM": 4}, total=150, arrivals=300)

    data = await latest_air_traffic(db_session)
    assert data["taken_at"] == T0
    assert data["india"] == {"aircraft_over_india": 150, "airborne": 145, "on_ground": 5}
    by = {a["airport"]: a for a in data["airports"]}
    assert [a["airport"] for a in data["airports"]] == ["BOM", "DEL"]  # table order
    assert by["DEL"]["live_congestion"] == "HIGH" and by["DEL"]["baseline_median"] == 10.0
    assert by["DEL"]["history_samples"] == 8 and by["DEL"]["arrivals_last_24h"] == 300
    assert by["BOM"]["live_congestion"] == "MODERATE" and by["BOM"]["city"] == "Mumbai"

    only = await latest_air_traffic(db_session, airports=("DEL", "XXX"))
    assert [a["airport"] for a in only["airports"]] == ["DEL"]


async def test_history(db_session):
    await _store(db_session, 20, {"DEL": 5}, total=90)
    await _store(db_session, 10, {"DEL": 6}, total=95)
    assert [r["aircraft_within_radius"] for r in await air_traffic_history(db_session, "DEL", 10)] == [6, 5]
    assert len(await air_traffic_history(db_session, "DEL", 1)) == 1
    assert [r["aircraft_over_india"] for r in await air_traffic_history(db_session, None, 10)] == [95, 90]
    assert await air_traffic_history(db_session, "BOM", 10) == []

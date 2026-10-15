from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from app.datasets import common
from app.datasets.openflights import AIRLINES_URL, ROUTES_URL, fetch_openflights, parse_airlines, parse_routes
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_SUCCESS, MarketRoute

FIXTURES = Path(__file__).parent / "fixtures" / "datasets"
ROUTES = (FIXTURES / "routes_excerpt.dat").read_text(encoding="utf-8")
AIRLINES = (FIXTURES / "airlines_excerpt.dat").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


def test_parse_airlines_maps_ids_and_codes_and_prefers_active():
    by_id, by_code = parse_airlines(AIRLINES)
    assert by_id["2850"] == "IndiGo Airlines"
    assert by_code["6E"] == "IndiGo Airlines" and by_code["IGO"] == "IndiGo Airlines"
    # G8 is shared by Go Air (active) and defunct airlines; the active one wins regardless of order.
    assert by_code["G8"] == "Go Air"
    assert "-1" not in by_id  # "Unknown" placeholder is dropped
    assert "-" not in by_code and "" not in by_code


def test_parse_airlines_skips_malformed_rows_and_nulls():
    by_id, by_code = parse_airlines('1,"A",\\N,"AA","AAA","","X","Y"\nshort,row\n\n\\N,"No id",\\N,"ZZ","ZZZ","","X","Y"\n')
    assert by_id == {"1": "A"}
    assert by_code == {"AA": "A", "AAA": "A"}


def test_parse_airlines_active_overrides_inactive_even_when_inactive_comes_first():
    _, by_code = parse_airlines('1,"Old",\\N,"QQ","QQQ","","X","N"\n2,"New",\\N,"QQ","QQR","","X","Y"\n')
    assert by_code["QQ"] == "New"


def test_parse_routes_keeps_only_twin_to_twin_routes():
    by_id, by_code = parse_airlines(AIRLINES)
    rows = parse_routes(ROUTES, by_id, by_code)
    assert rows
    assert {r["origin"] for r in rows} <= {"BOM", "DEL", "BLR", "MAA", "HYD", "CCU"}
    assert {r["destination"] for r in rows} <= {"BOM", "DEL", "BLR", "MAA", "HYD", "CCU"}
    assert not any(r["origin"] == "JFK" for r in rows)
    indigo = [r for r in rows if r["airline_code"] == "6E" and r["origin"] == "BLR" and r["destination"] == "BOM"]
    assert len(indigo) == 1 and indigo[0]["airline_name"] == "IndiGo Airlines" and indigo[0]["stops"] == 0
    assert indigo[0]["equipment"] == "320"
    # (airline, origin, destination) is unique, and null airline ids (\N) do not break the key.
    assert len({(r["airline_code"], r["origin"], r["destination"]) for r in rows}) == len(rows)


def test_parse_routes_handles_edge_cases():
    text = "\n".join(
        [
            "6E,2850,BOM,1,DEL,2,,0,320",
            "6E,2850,BOM,1,DEL,2,,0,320",  # duplicate
            "6E,2850,BOM,1,DEL,2,Y,0,320",  # codeshare is skipped
            "AI,218,DEL,1,BOM,2,,0,\\N",  # null equipment
            "AI,218,DEL,1,DEL,2,,0,320",  # same origin and destination
            "AI,218,DEL,1,BOM,2,,x,320",  # bad stops
            "short,row",
            "",
            "\\N,\\N,BOM,1,DEL,2,,0,320",  # no airline
            "XX,\\N,BOM,1,DEL,2,,1,737 738",  # unknown airline, null id, one stop
        ]
    )
    rows = parse_routes(text, {"2850": "IndiGo Airlines"}, {"XX": "Fallback Name"})
    assert [(r["airline_code"], r["origin"], r["destination"]) for r in rows] == [
        ("6E", "BOM", "DEL"),
        ("AI", "DEL", "BOM"),
        ("XX", "BOM", "DEL"),
    ]
    assert rows[1]["equipment"] == "" and rows[1]["airline_name"] is None
    assert rows[2]["airline_name"] == "Fallback Name" and rows[2]["stops"] == 1


def test_parse_routes_empty_input():
    assert parse_routes("", {}, {}) == []


@respx.mock
async def test_fetch_openflights_stores_files_rows_and_snapshot(db_session, tmp_path):
    respx.get(ROUTES_URL).mock(return_value=httpx.Response(200, content=ROUTES.encode()))
    respx.get(AIRLINES_URL).mock(return_value=httpx.Response(200, content=AIRLINES.encode()))

    snap = await fetch_openflights(db_session, base_dir=tmp_path)

    assert snap.status == SNAPSHOT_SUCCESS and snap.row_count > 0
    assert Path(snap.local_path).read_text(encoding="utf-8") == ROUTES
    assert len(snap.checksum) == 64
    stored = (await db_session.execute(select(MarketRoute))).scalars().all()
    assert len(stored) == snap.row_count
    assert {m.snapshot_id for m in stored} == {snap.id}


@respx.mock
async def test_fetch_openflights_replaces_previous_rows(db_session, tmp_path):
    respx.get(ROUTES_URL).mock(return_value=httpx.Response(200, content=ROUTES.encode()))
    respx.get(AIRLINES_URL).mock(return_value=httpx.Response(200, content=AIRLINES.encode()))
    first = await fetch_openflights(db_session, base_dir=tmp_path)
    second = await fetch_openflights(db_session, base_dir=tmp_path)

    stored = (await db_session.execute(select(MarketRoute))).scalars().all()
    assert len(stored) == first.row_count == second.row_count
    assert {m.snapshot_id for m in stored} == {second.id}


@respx.mock
async def test_fetch_openflights_failure_keeps_previous_rows(db_session, tmp_path):
    respx.get(ROUTES_URL).mock(return_value=httpx.Response(200, content=ROUTES.encode()))
    respx.get(AIRLINES_URL).mock(return_value=httpx.Response(200, content=AIRLINES.encode()))
    good = await fetch_openflights(db_session, base_dir=tmp_path)

    respx.get(ROUTES_URL).mock(return_value=httpx.Response(200, content=b""))
    bad = await fetch_openflights(db_session, base_dir=tmp_path)

    assert bad.status == SNAPSHOT_FAILED and "no routes" in bad.error
    stored = (await db_session.execute(select(MarketRoute))).scalars().all()
    assert len(stored) == good.row_count


@respx.mock
async def test_fetch_openflights_http_error_is_a_failed_snapshot(db_session, tmp_path):
    respx.get(ROUTES_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    respx.get(AIRLINES_URL).mock(return_value=httpx.Response(200, content=AIRLINES.encode()))
    snap = await fetch_openflights(db_session, base_dir=tmp_path)
    assert snap.status == SNAPSHOT_FAILED and "failed" in snap.error

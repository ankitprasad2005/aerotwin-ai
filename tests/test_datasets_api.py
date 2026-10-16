from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import datasets as datasets_api
from app.api.datasets import router
from app.api.deps import get_db
from app.models.external import (
    SNAPSHOT_FAILED,
    SNAPSHOT_SUCCESS,
    DatasetSnapshot,
    OilPrice,
    DgcaTraffic,
    FuelPrice,
    FxRate,
    MarketRoute,
)


def _client(db_session) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _snapshot(source, status=SNAPSHOT_SUCCESS, minutes=0, rows=3, error=None):
    return DatasetSnapshot(
        source=source,
        fetched_at=datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes),
        status=status,
        source_url="https://x",
        row_count=rows,
        error=error,
    )


async def test_list_datasets_without_snapshots(db_session):
    async with _client(db_session) as client:
        response = await client.get("/api/datasets")

    body = response.json()
    assert response.status_code == 200
    assert {"openflights", "eia_jet_fuel", "eia_brent", "fx", "dgca", "aviation_weather", "open_meteo", "faa_airworthiness_directives", "aviation_weather_taf", "world_bank"} <= {d["source"] for d in body}
    assert body[0]["source"] == "openflights"
    assert all(d["latest"] is None for d in body)
    assert all(d["title"] and d["description"] and d["license"] and d["source_url"] for d in body)
    assert "ODbL" in body[0]["license"]


async def test_list_datasets_reports_the_most_recent_snapshot(db_session):
    db_session.add_all(
        [
            _snapshot("fx", rows=1, minutes=0),
            _snapshot("fx", status=SNAPSHOT_FAILED, rows=0, minutes=5, error="boom"),
            _snapshot("eia_jet_fuel", rows=9),
        ]
    )
    await db_session.flush()

    async with _client(db_session) as client:
        body = {d["source"]: d for d in (await client.get("/api/datasets")).json()}

    assert body["fx"]["latest"]["status"] == SNAPSHOT_FAILED
    assert body["fx"]["latest"]["error"] == "boom" and body["fx"]["latest"]["row_count"] == 0
    assert body["eia_jet_fuel"]["latest"]["row_count"] == 9
    assert body["openflights"]["latest"] is None


async def test_refresh_passes_sources_and_returns_results(db_session, monkeypatch):
    calls = []

    async def fake_refresh(db, sources=None):
        calls.append(sources)
        return [_snapshot("fx", rows=4)]

    monkeypatch.setattr(datasets_api, "refresh_all", fake_refresh)

    async with _client(db_session) as client:
        r1 = await client.post("/api/datasets/refresh", json={"sources": ["fx"]})
        r2 = await client.post("/api/datasets/refresh", json={})
        r3 = await client.post("/api/datasets/refresh")

    assert calls == [["fx"], None, None]
    assert r1.status_code == 200
    (result,) = r1.json()
    assert {k: result[k] for k in ("source", "status", "row_count", "error")} == {
        "source": "fx", "status": "SUCCESS", "row_count": 4, "error": None
    }
    assert result["fetched_at"].startswith("2026-10-15T08:00:00")
    assert r2.status_code == r3.status_code == 200


@pytest.mark.parametrize("body", [{"sources": ["nope"]}, {"sources": ["fx", "nope"]}, {"sources": "fx"}, {"sources": [1]}])
async def test_refresh_rejects_unknown_or_malformed_sources(db_session, monkeypatch, body):
    async def fail(*a, **k):
        raise AssertionError("must not run")

    monkeypatch.setattr(datasets_api, "refresh_all", fail)
    async with _client(db_session) as client:
        response = await client.post("/api/datasets/refresh", json=body)
    assert response.status_code == 422


async def test_fuel_prices_ascending_and_limited_to_days(db_session):
    today = date.today()
    db_session.add_all(
        [
            FuelPrice(series="s", price_date=today - timedelta(days=d), usd_per_gallon=2.0 + d)
            for d in (0, 5, 40, 100)
        ]
    )
    await db_session.flush()

    async with _client(db_session) as client:
        default = (await client.get("/api/datasets/fuel-prices")).json()
        short = (await client.get("/api/datasets/fuel-prices", params={"days": 10})).json()
        longest = (await client.get("/api/datasets/fuel-prices", params={"days": 3650})).json()

    assert [p["usd_per_gallon"] for p in default] == [42.0, 7.0, 2.0]  # 100 days ago is outside the default 90
    assert [p["usd_per_gallon"] for p in short] == [7.0, 2.0]
    assert len(longest) == 4
    assert default[0]["date"] == (today - timedelta(days=40)).isoformat()


@pytest.mark.parametrize("path", ["/api/datasets/fuel-prices", "/api/datasets/brent-prices", "/api/datasets/fx-rates"])
@pytest.mark.parametrize("days,status", [(0, 422), (-1, 422), (3651, 422), ("abc", 422), (1, 200), (3650, 200)])
async def test_days_bounds(db_session, path, days, status):
    async with _client(db_session) as client:
        response = await client.get(path, params={"days": days})
    assert response.status_code == status


async def test_fx_rates_filters_quote_and_days(db_session):
    today = date.today()
    db_session.add_all(
        [
            FxRate(base="USD", quote="INR", rate_date=today - timedelta(days=1), rate=90.5),
            FxRate(base="USD", quote="INR", rate_date=today - timedelta(days=200), rate=80.0),
            FxRate(base="USD", quote="EUR", rate_date=today - timedelta(days=1), rate=0.9),
        ]
    )
    await db_session.flush()

    async with _client(db_session) as client:
        inr = (await client.get("/api/datasets/fx-rates")).json()
        eur = (await client.get("/api/datasets/fx-rates", params={"quote": "eur"})).json()
        none = (await client.get("/api/datasets/fx-rates", params={"quote": "JPY"})).json()
        bad = await client.get("/api/datasets/fx-rates", params={"quote": "INRX"})

    assert inr == [{"date": (today - timedelta(days=1)).isoformat(), "rate": 90.5}]
    assert [r["rate"] for r in eur] == [0.9]
    assert none == []
    assert bad.status_code == 422


async def test_market_routes_filters(db_session):
    db_session.add_all(
        [
            MarketRoute(airline_code="6E", airline_name="IndiGo", origin="BOM", destination="DEL", stops=0, equipment="320"),
            MarketRoute(airline_code="AI", airline_name="Air India", origin="BOM", destination="DEL"),
            MarketRoute(airline_code="6E", airline_name="IndiGo", origin="DEL", destination="BOM"),
        ]
    )
    await db_session.flush()

    async with _client(db_session) as client:
        everything = (await client.get("/api/datasets/market-routes")).json()
        both = (await client.get("/api/datasets/market-routes", params={"origin": "bom", "destination": "del"})).json()
        origin_only = (await client.get("/api/datasets/market-routes", params={"origin": "DEL"})).json()
        dest_only = (await client.get("/api/datasets/market-routes", params={"destination": "DEL"})).json()
        nothing = (await client.get("/api/datasets/market-routes", params={"origin": "ZZZ"})).json()
        too_long = await client.get("/api/datasets/market-routes", params={"origin": "TOOLONG"})

    assert len(everything) == 3
    assert [m["airline_name"] for m in both] == ["Air India", "IndiGo"]
    assert both[1] == {
        "airline_code": "6E", "airline_name": "IndiGo", "origin": "BOM", "destination": "DEL", "stops": 0, "equipment": "320"
    }
    assert [m["destination"] for m in origin_only] == ["BOM"]
    assert len(dest_only) == 2
    assert nothing == []
    assert too_long.status_code == 422


async def test_dgca_traffic_latest_period_first(db_session):
    def row(period, airline, share, fallback=False):
        return DgcaTraffic(
            period=period, airline=airline, passengers=1, market_share_pct=share, load_factor_pct=80.0,
            source_url="https://x", is_fallback=fallback,
        )

    db_session.add_all([row("2026-03", "Old", 90.0, True), row("2026-04", "B", 30.0), row("2026-04", "A", 60.0), row("2026-04", "N", None)])
    await db_session.flush()

    async with _client(db_session) as client:
        body = (await client.get("/api/datasets/dgca-traffic")).json()

    assert [(r["period"], r["airline"]) for r in body] == [
        ("2026-04", "A"), ("2026-04", "B"), ("2026-04", "N"), ("2026-03", "Old")
    ]
    assert body[3]["is_fallback"] is True and body[0]["is_fallback"] is False


async def test_empty_tables_return_empty_lists(db_session):
    async with _client(db_session) as client:
        for path in ("fuel-prices", "brent-prices", "fx-rates", "market-routes", "dgca-traffic"):
            response = await client.get(f"/api/datasets/{path}")
            assert response.status_code == 200 and response.json() == []


async def test_brent_prices_exact_shape_ascending_and_limited_to_days(db_session):
    today = date.today()
    db_session.add_all(
        [OilPrice(series="RBRTE", price_date=today - timedelta(days=d), usd_per_barrel=70.0 + d) for d in (0, 5, 40, 100)]
    )
    await db_session.flush()

    async with _client(db_session) as client:
        default = (await client.get("/api/datasets/brent-prices")).json()
        short = (await client.get("/api/datasets/brent-prices", params={"days": 10})).json()

    assert default == [
        {"date": (today - timedelta(days=40)).isoformat(), "usd_per_barrel": 110.0},
        {"date": (today - timedelta(days=5)).isoformat(), "usd_per_barrel": 75.0},
        {"date": today.isoformat(), "usd_per_barrel": 70.0},
    ]
    assert [p["usd_per_barrel"] for p in short] == [75.0, 70.0]

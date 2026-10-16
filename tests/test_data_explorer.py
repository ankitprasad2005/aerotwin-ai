import csv
import io
import uuid
from datetime import date, datetime, timezone

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect as sa_inspect

from app.api.data_explorer import router
from app.api.deps import get_db
from app.datasets import explorer
from app.db import Base
from app.models import digital_twin, external, observability  # noqa: F401
from app.models.external import AirworthinessDirective, DatasetSnapshot, FuelPrice, MarketRoute, WeatherForecast


def _client(db_session) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_fuel(db, n=5):
    for i in range(n):
        db.add(FuelPrice(series="jet", price_date=date(2026, 10, 1 + i), usd_per_gallon=2.0 + i))
    await db.commit()


# --- registry ---------------------------------------------------------------------------------

def test_every_model_is_registered_or_excluded_with_reason():
    registered = {t.model.__tablename__ for t in explorer.EXPLORER_TABLES.values()}
    excluded = set(explorer.EXCLUDED_TABLES)
    assert registered.isdisjoint(excluded)
    all_tables = {m.class_.__tablename__ for m in Base.registry.mappers if m.class_.__module__.startswith("app.models")}
    assert all_tables - registered - excluded == set()
    assert all(reason.strip() for reason in explorer.EXCLUDED_TABLES.values())


def test_registry_entries_are_consistent():
    for key, table in explorer.EXPLORER_TABLES.items():
        assert table.category in explorer.CATEGORIES, key
        names = [c.name for c in table.columns]
        assert len(names) == len(set(names)), key
        mapped = set(sa_inspect(table.model).columns.keys())
        assert set(names) <= mapped, key
        assert set(table.searchable) <= set(names), key
        assert table.default_sort[0] in names, key
        assert table.default_sort[1] in ("asc", "desc")
        assert all(c.type in explorer.COLUMN_TYPES for c in table.columns), key


def test_required_tables_present():
    for key in ("market_routes", "fuel_prices", "oil_prices", "fx_rates", "dgca_traffic", "weather_observations",
                "weather_forecasts", "weather_tafs", "airworthiness_directives", "world_bank_indicators",
                "web_search_cache", "dataset_snapshots", "airports", "aircraft", "routes", "crew_members",
                "maintenance_records", "passenger_demand", "cargo_demand"):
        assert key in explorer.EXPLORER_TABLES


# --- catalog ----------------------------------------------------------------------------------

async def test_catalog_lists_tables_with_counts_and_refresh(db_session):
    await _seed_fuel(db_session, 3)
    db_session.add(DatasetSnapshot(source="eia_jet_fuel", fetched_at=datetime(2026, 10, 15, 8, tzinfo=timezone.utc),
                                   status="SUCCESS", source_url="x", row_count=3))
    await db_session.commit()
    async with _client(db_session) as c:
        body = (await c.get("/api/data/catalog")).json()
    by_key = {e["key"]: e for e in body}
    assert set(by_key) == set(explorer.EXPLORER_TABLES)
    fuel = by_key["fuel_prices"]
    assert fuel["row_count"] == 3
    assert fuel["last_refreshed"].startswith("2026-10-15T08:00")
    assert fuel["category"] == "Fuel & prices"
    assert {"name": "usd_per_gallon", "label": "USD per gallon", "type": "number", "unit": "USD/gal"} in fuel["columns"]
    assert by_key["fx_rates"]["last_refreshed"] is None
    assert by_key["airports"]["last_refreshed"] is None


# --- rows -------------------------------------------------------------------------------------

async def test_rows_pagination_and_default_sort(db_session):
    await _seed_fuel(db_session, 5)
    async with _client(db_session) as c:
        r = (await c.get("/api/data/fuel_prices/rows?limit=2&offset=1")).json()
        assert r["total"] == 5
        assert [x["price_date"] for x in r["rows"]] == ["2026-10-04", "2026-10-03"]  # default newest first
        assert len((await c.get("/api/data/fuel_prices/rows")).json()["rows"]) == 5


async def test_rows_sort_and_order(db_session):
    await _seed_fuel(db_session, 3)
    async with _client(db_session) as c:
        r = (await c.get("/api/data/fuel_prices/rows?sort=usd_per_gallon&order=asc")).json()
    assert [x["usd_per_gallon"] for x in r["rows"]] == [2.0, 3.0, 4.0]


async def test_rows_search_is_case_insensitive_and_escapes_wildcards(db_session):
    db_session.add_all([
        MarketRoute(airline_code="AI", airline_name="Air India", origin="DEL", destination="BOM"),
        MarketRoute(airline_code="6E", airline_name="IndiGo", origin="DEL", destination="BLR"),
        MarketRoute(airline_code="XX", airline_name="100% Air", origin="DEL", destination="GOI"),
    ])
    await db_session.commit()
    async with _client(db_session) as c:
        assert (await c.get("/api/data/market_routes/rows?q=INDIGO")).json()["total"] == 1
        assert (await c.get("/api/data/market_routes/rows?q=blr")).json()["total"] == 1
        assert (await c.get("/api/data/market_routes/rows?q=%25")).json()["total"] == 1
        assert (await c.get("/api/data/market_routes/rows?q=")).json()["total"] == 3


async def test_rows_filters(db_session):
    await _seed_fuel(db_session, 4)
    db_session.add(FuelPrice(series="other", price_date=date(2026, 9, 1), usd_per_gallon=9.5))
    await db_session.commit()
    async with _client(db_session) as c:
        assert (await c.get("/api/data/fuel_prices/rows?filter.series=OTH")).json()["total"] == 1
        assert (await c.get("/api/data/fuel_prices/rows?filter.usd_per_gallon=9.5")).json()["total"] == 1
        assert (await c.get("/api/data/fuel_prices/rows?filter.price_date=2026-10-02")).json()["total"] == 1
        both = await c.get("/api/data/fuel_prices/rows?filter.series=jet&q=jet&filter.usd_per_gallon=3")
        assert both.json()["total"] == 1


async def test_rows_json_safe_values(db_session):
    snap = DatasetSnapshot(source="s", fetched_at=datetime(2026, 10, 15, tzinfo=timezone.utc), status="SUCCESS",
                           source_url="u", row_count=1, details={"a": [1, 2]})
    db_session.add(snap)
    await db_session.flush()
    db_session.add(AirworthinessDirective(document_number="D1", title="T", publication_date=date(2026, 1, 2),
                                          html_url="h", aircraft_types=["A320"], snapshot_id=snap.id))
    await db_session.commit()
    async with _client(db_session) as c:
        ad = (await c.get("/api/data/airworthiness_directives/rows")).json()["rows"][0]
        assert ad["aircraft_types"] == ["A320"] and ad["publication_date"] == "2026-01-02"
        assert (await c.get("/api/data/airworthiness_directives/rows?filter.aircraft_types=a320")).json()["total"] == 1
        s = (await c.get("/api/data/dataset_snapshots/rows")).json()["rows"][0]
        assert s["details"] == {"a": [1, 2]}
        assert s["fetched_at"].startswith("2026-10-15T00:00:00")
        uuid.UUID(s["id"])


async def test_rows_validation(db_session):
    async with _client(db_session) as c:
        assert (await c.get("/api/data/nope/rows")).status_code == 404
        assert (await c.get("/api/data/nope/export.csv")).status_code == 404
        assert (await c.get("/api/data/fuel_prices/rows?sort=bogus")).status_code == 422
        assert (await c.get("/api/data/fuel_prices/rows?filter.bogus=1")).status_code == 422
        assert (await c.get("/api/data/fuel_prices/rows?filter.usd_per_gallon=abc")).status_code == 422
        assert (await c.get("/api/data/fuel_prices/rows?filter.price_date=notadate")).status_code == 422
        assert (await c.get("/api/data/fuel_prices/rows?limit=501")).status_code == 422
        assert (await c.get("/api/data/fuel_prices/rows?limit=0")).status_code == 422
        assert (await c.get("/api/data/fuel_prices/rows?offset=-1")).status_code == 422
        assert (await c.get("/api/data/fuel_prices/rows?order=up")).status_code == 422


async def test_boolean_and_integer_filters(db_session):
    for i, ts in enumerate([True, False, False]):
        db_session.add(WeatherForecast(airport="BOM", forecast_date=date(2026, 10, 1 + i), precipitation_mm=1,
                                       max_gust_kmh=2, weather_code=i, thunderstorm=ts))
    await db_session.commit()
    async with _client(db_session) as c:
        assert (await c.get("/api/data/weather_forecasts/rows?filter.thunderstorm=true")).json()["total"] == 1
        assert (await c.get("/api/data/weather_forecasts/rows?filter.thunderstorm=no")).json()["total"] == 2
        assert (await c.get("/api/data/weather_forecasts/rows?filter.weather_code=2")).json()["total"] == 1
        assert (await c.get("/api/data/weather_forecasts/rows?filter.thunderstorm=maybe")).status_code == 422


# --- csv --------------------------------------------------------------------------------------

async def test_export_csv_streams_filtered_rows(db_session):
    await _seed_fuel(db_session, 4)
    async with _client(db_session) as c:
        resp = await c.get("/api/data/fuel_prices/export.csv?sort=usd_per_gallon&order=asc&filter.usd_per_gallon=3")
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'filename="fuel_prices.csv"' in resp.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert rows[0] == [c.name for c in explorer.EXPLORER_TABLES["fuel_prices"].columns]
    assert len(rows) == 2 and "3.0" in rows[1]


async def test_export_csv_json_and_batches(db_session, monkeypatch):
    monkeypatch.setattr(explorer, "CSV_BATCH", 2)
    await _seed_fuel(db_session, 5)
    db_session.add(AirworthinessDirective(document_number="D1", title='a, "b"', publication_date=date(2026, 1, 2),
                                          html_url="h", aircraft_types=["A320"]))
    await db_session.commit()
    async with _client(db_session) as c:
        fuel = await c.get("/api/data/fuel_prices/export.csv")
        ad = await c.get("/api/data/airworthiness_directives/export.csv")
        assert (await c.get("/api/data/fuel_prices/export.csv?sort=zzz")).status_code == 422
    assert len(list(csv.reader(io.StringIO(fuel.text)))) == 6
    row = list(csv.DictReader(io.StringIO(ad.text)))[0]
    assert row["title"] == 'a, "b"' and row["aircraft_types"] == '["A320"]'

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.external import (
    DatasetSnapshot, DecisionWeightProfile, DgcaTraffic, FuelPrice, FxRate, MarketRoute, WebSearchCache,
)

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


async def test_dataset_snapshot_defaults_and_round_trip(db_session):
    snap = DatasetSnapshot(source="openflights", fetched_at=NOW, status="SUCCESS", source_url="http://x")
    db_session.add(snap)
    await db_session.flush()
    await db_session.refresh(snap)
    assert snap.row_count == 0
    assert snap.details == {}
    assert snap.local_path is None and snap.checksum is None and snap.error is None
    snap.details = {"a": [1, 2]}
    snap.error = "boom"
    await db_session.flush()
    fetched = (await db_session.execute(select(DatasetSnapshot))).scalar_one()
    assert fetched.details == {"a": [1, 2]} and fetched.error == "boom"


async def test_dataset_snapshot_requires_source(db_session):
    db_session.add(DatasetSnapshot(fetched_at=NOW, status="SUCCESS", source_url="x"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_market_route_defaults_and_snapshot_link(db_session):
    snap = DatasetSnapshot(source="openflights", fetched_at=NOW, status="SUCCESS", source_url="x")
    db_session.add(snap)
    await db_session.flush()
    route = MarketRoute(airline_code="6E", origin="BOM", destination="DEL", snapshot_id=snap.id)
    db_session.add(route)
    await db_session.flush()
    assert route.stops == 0 and route.equipment == "" and route.airline_name is None
    assert route.snapshot_id == snap.id


async def test_market_route_snapshot_is_optional(db_session):
    db_session.add(MarketRoute(airline_code="AI", origin="BOM", destination="DEL"))
    await db_session.flush()


async def test_market_route_airport_code_length_overflow_rejected(db_session):
    db_session.add(MarketRoute(airline_code="AI", origin="TOOLONG", destination="DEL"))
    with pytest.raises(DBAPIError):
        await db_session.flush()


async def test_fuel_price_unique_per_series_and_date(db_session):
    db_session.add(FuelPrice(series="eia", price_date=date(2026, 10, 10), usd_per_gallon=2.1))
    db_session.add(FuelPrice(series="eia", price_date=date(2026, 10, 11), usd_per_gallon=2.2))
    db_session.add(FuelPrice(series="other", price_date=date(2026, 10, 10), usd_per_gallon=2.3))
    await db_session.flush()
    db_session.add(FuelPrice(series="eia", price_date=date(2026, 10, 10), usd_per_gallon=9.9))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_fx_rate_unique_per_pair_and_date(db_session):
    db_session.add(FxRate(base="USD", quote="INR", rate_date=date(2026, 10, 10), rate=83.1))
    db_session.add(FxRate(base="USD", quote="EUR", rate_date=date(2026, 10, 10), rate=0.9))
    await db_session.flush()
    db_session.add(FxRate(base="USD", quote="INR", rate_date=date(2026, 10, 10), rate=84.0))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_dgca_traffic_defaults_nullable_metrics_and_unique(db_session):
    row = DgcaTraffic(period="2026-04", airline="IndiGo", source_url="x")
    db_session.add(row)
    await db_session.flush()
    assert row.is_fallback is False
    assert row.passengers is None and row.market_share_pct is None and row.load_factor_pct is None
    db_session.add(DgcaTraffic(period="2026-04", airline="Air India", source_url="x", is_fallback=True))
    await db_session.flush()
    db_session.add(DgcaTraffic(period="2026-04", airline="IndiGo", source_url="y"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_web_search_cache_round_trip_and_unique_query(db_session):
    db_session.add(WebSearchCache(query="jet fuel", results=[{"title": "t"}], result_count=1, fetched_at=NOW))
    await db_session.flush()
    fetched = (await db_session.execute(select(WebSearchCache))).scalar_one()
    assert fetched.results == [{"title": "t"}] and fetched.result_count == 1
    db_session.add(WebSearchCache(query="jet fuel", results=[], result_count=0, fetched_at=NOW))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_web_search_cache_results_default_to_empty_list(db_session):
    row = WebSearchCache(query="q", result_count=0, fetched_at=NOW)
    db_session.add(row)
    await db_session.flush()
    await db_session.refresh(row)
    assert row.results == []


async def test_decision_weight_profile_unique_name(db_session):
    db_session.add(DecisionWeightProfile(name="default", weights={"profit": 0.5}))
    await db_session.flush()
    db_session.add(DecisionWeightProfile(name="default", weights={}))
    with pytest.raises(IntegrityError):
        await db_session.flush()

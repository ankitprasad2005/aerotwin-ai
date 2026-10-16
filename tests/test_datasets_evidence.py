from datetime import date, datetime, timedelta, timezone

import pytest

from app.datasets.evidence import (
    dgca_market,
    brent_price,
    fuel_price,
    fx_rate,
    market_competition,
    parse_route,
    pct_change,
)
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.models.external import (
    SNAPSHOT_FAILED,
    SNAPSHOT_SUCCESS,
    DatasetSnapshot,
    DgcaTraffic,
    FuelPrice,
    FxRate,
    MarketRoute,
)
from app.seed.seed import run_seed


def _request(route=None):
    return EvidenceRequest(agent_type="NETWORK", objective="x", route=route, previous_results=[])


@pytest.mark.parametrize(
    "value,expected",
    [("BOM-DEL", ("BOM", "DEL")), (" bom-del ", ("BOM", "DEL")), (None, None), ("", None), ("BOM", None),
     ("BOM-", None), ("-DEL", None), ("A-B-C", None)],
)
def test_parse_route(value, expected):
    assert parse_route(value) == expected


def test_pct_change():
    assert pct_change(110.0, 100.0) == 10.0
    assert pct_change(90.0, 100.0) == -10.0
    assert pct_change(1.0, None) is None
    assert pct_change(1.0, 0) is None


async def test_every_provider_returns_empty_when_tables_are_empty(db_session):
    for provider in (market_competition, fuel_price, brent_price, fx_rate, dgca_market):
        assert await provider(db_session, _request()) == []
        assert await provider(db_session, _request("BOM-DEL")) == []


# --- market competition -----------------------------------------------------------------------


async def _market(db_session):
    db_session.add(
        DatasetSnapshot(
            source="openflights", fetched_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            status=SNAPSHOT_SUCCESS, source_url="https://x", row_count=3,
        )
    )
    db_session.add_all(
        [
            MarketRoute(airline_code="6E", airline_name="IndiGo", origin="BOM", destination="DEL", stops=0, equipment="320"),
            MarketRoute(airline_code="AI", airline_name="Air India", origin="BOM", destination="DEL", stops=0, equipment="321"),
            MarketRoute(airline_code="6E", airline_name="IndiGo", origin="BOM", destination="BLR"),
        ]
    )
    await db_session.flush()


async def test_market_competition_for_a_route(db_session):
    await _market(db_session)

    (item,) = await market_competition(db_session, _request("BOM-DEL"))

    assert isinstance(item, EvidenceItem)
    assert item.id == "market:BOM-DEL" and item.source == "openflights" and item.kind == "dataset"
    assert item.reliability == 0.7
    assert item.fetched_at == datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert item.content["rival_count"] == 2
    assert [a["name"] for a in item.content["airlines"]] == ["Air India", "IndiGo"]


async def test_market_competition_route_without_data_or_malformed_route(db_session):
    await _market(db_session)
    assert await market_competition(db_session, _request("BOM-HYD")) == []
    assert await market_competition(db_session, _request("garbage")) == []


async def test_market_competition_without_route_covers_each_twin_route(db_session):
    await run_seed(db_session)
    await _market(db_session)

    items = await market_competition(db_session, _request(None))

    assert {i.id for i in items} == {"market:BOM-DEL", "market:BOM-BLR"}  # twin routes that have market data


async def test_market_competition_ignores_failed_snapshots_for_fetched_at(db_session):
    db_session.add(
        DatasetSnapshot(
            source="openflights", fetched_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
            status=SNAPSHOT_FAILED, source_url="https://x", row_count=0,
        )
    )
    db_session.add(MarketRoute(airline_code="6E", airline_name="IndiGo", origin="BOM", destination="DEL"))
    await db_session.flush()

    (item,) = await market_competition(db_session, _request("BOM-DEL"))
    assert item.fetched_at is None


async def test_market_competition_with_no_twin_routes_and_no_route(db_session):
    await db_session.flush()
    assert await market_competition(db_session, _request(None)) == []


# --- fuel ----------------------------------------------------------------------------------------


async def test_fuel_price_latest_averages_and_change(db_session):
    latest = date(2026, 10, 10)
    # price = 2 + days_ago / 100 -> older is higher? use a clear shape: 30 days ago = 2.0, latest = 2.2.
    points = {0: 2.2, 10: 2.1, 30: 2.0, 60: 1.9, 120: 1.0}
    db_session.add_all(
        FuelPrice(series="s", price_date=latest - timedelta(days=d), usd_per_gallon=p) for d, p in points.items()
    )
    await db_session.flush()

    (item,) = await fuel_price(db_session, _request())

    assert item.id == "fuel:eia:2026-10-10" and item.source == "eia_jet_fuel" and item.reliability == 0.9
    assert item.content["latest_usd_per_gallon"] == 2.2
    assert item.content["latest_date"] == "2026-10-10"
    assert item.content["avg_30d_usd_per_gallon"] == pytest.approx((2.2 + 2.1 + 2.0) / 3, abs=1e-4)
    assert item.content["avg_90d_usd_per_gallon"] == pytest.approx((2.2 + 2.1 + 2.0 + 1.9) / 4, abs=1e-4)
    assert item.content["change_pct_vs_30d_ago"] == 10.0
    assert item.fetched_at is not None


async def test_fuel_price_single_row_has_no_change(db_session):
    db_session.add(FuelPrice(series="s", price_date=date(2026, 10, 10), usd_per_gallon=3.0))
    await db_session.flush()

    (item,) = await fuel_price(db_session, _request())

    assert item.content["avg_30d_usd_per_gallon"] == 3.0 == item.content["avg_90d_usd_per_gallon"]
    assert item.content["change_pct_vs_30d_ago"] is None


# --- fx ------------------------------------------------------------------------------------------


async def test_fx_rate_latest_and_change(db_session):
    latest = date(2026, 10, 14)
    db_session.add_all(
        [
            FxRate(base="USD", quote="INR", rate_date=latest, rate=88.0),
            FxRate(base="USD", quote="INR", rate_date=latest - timedelta(days=31), rate=80.0),
            FxRate(base="USD", quote="EUR", rate_date=latest, rate=0.9),
        ]
    )
    await db_session.flush()

    (item,) = await fx_rate(db_session, _request())

    assert item.id == "fx:usd_inr:2026-10-14" and item.source == "fx" and item.reliability == 0.95
    assert item.content["usd_inr"] == 88.0 and item.content["change_pct_vs_30d_ago"] == 10.0


async def test_fx_rate_ignores_other_quotes_and_handles_no_history(db_session):
    db_session.add(FxRate(base="USD", quote="EUR", rate_date=date(2026, 10, 14), rate=0.9))
    await db_session.flush()
    assert await fx_rate(db_session, _request()) == []

    db_session.add(FxRate(base="USD", quote="INR", rate_date=date(2026, 10, 14), rate=88.0))
    await db_session.flush()
    (item,) = await fx_rate(db_session, _request())
    assert item.content["change_pct_vs_30d_ago"] is None


# --- dgca ----------------------------------------------------------------------------------------


def _traffic(period, airline, share, load, passengers=1000, fallback=False):
    return DgcaTraffic(
        period=period, airline=airline, passengers=passengers, market_share_pct=share, load_factor_pct=load,
        source_url=f"https://dgca/{period}.pdf", is_fallback=fallback,
    )


async def test_dgca_market_top_airlines_for_the_latest_period(db_session):
    db_session.add_all(
        [_traffic("2026-03", "Old", 99.0, 50.0)]
        + [_traffic("2026-04", f"A{i}", 10.0 + i, 80.0 + i) for i in range(7)]
        + [_traffic("2026-04", "NoShare", None, None)]
    )
    await db_session.flush()

    (item,) = await dgca_market(db_session, _request())

    assert item.id == "dgca:2026-04" and item.source == "dgca" and item.reliability == 0.9
    assert item.url == "https://dgca/2026-04.pdf"
    top = item.content["top_airlines"]
    assert [a["airline"] for a in top] == ["A6", "A5", "A4", "A3", "A2"]  # capped at 5, by share
    assert item.content["industry_avg_load_factor_pct"] == 83.0  # mean(80..86), NoShare has no load factor
    assert item.content["is_fallback"] is False and item.content["period"] == "2026-04"


async def test_dgca_market_flags_fallback_and_handles_missing_load_factors(db_session):
    db_session.add(_traffic("2026-04", "OnlyAir", 100.0, None, fallback=True))
    await db_session.flush()

    (item,) = await dgca_market(db_session, _request())

    assert item.content["is_fallback"] is True
    assert item.content["industry_avg_load_factor_pct"] is None


def test_providers_are_wired_into_the_catalog():
    from app.evidence.catalog import EVIDENCE_PROVIDERS

    assert EVIDENCE_PROVIDERS["fuel_price"] is fuel_price
    assert EVIDENCE_PROVIDERS["fx_rate"] is fx_rate
    assert EVIDENCE_PROVIDERS["market_competition"] is market_competition
    assert EVIDENCE_PROVIDERS["dgca_market"] is dgca_market


# --- brent ---------------------------------------------------------------------------------------


async def test_brent_price_latest_average_change_and_crack_spread(db_session):
    from app.models.external import OilPrice

    latest = date(2026, 10, 10)
    points = {0: 88.0, 10: 84.0, 30: 80.0, 60: 70.0}
    db_session.add_all(
        OilPrice(series="RBRTE", price_date=latest - timedelta(days=d), usd_per_barrel=p) for d, p in points.items()
    )
    db_session.add(FuelPrice(series="s", price_date=date(2026, 10, 9), usd_per_gallon=3.0))
    await db_session.flush()

    (item,) = await brent_price(db_session, _request())

    assert item.id == "brent:eia:2026-10-10" and item.source == "eia_brent" and item.reliability == 0.9
    assert item.content["latest_usd_per_barrel"] == 88.0 and item.content["latest_date"] == "2026-10-10"
    assert item.content["avg_30d_usd_per_barrel"] == pytest.approx((88 + 84 + 80) / 3, abs=1e-4)
    assert item.content["change_pct_vs_30d_ago"] == 10.0
    # jet 3.0 USD/gal x 42 gal/bbl = 126.0 USD/bbl, minus Brent 88.0
    assert item.content["jet_fuel_crack_spread_usd_per_barrel"] == 38.0
    assert item.fetched_at is not None


async def test_brent_price_without_jet_fuel_or_history_has_no_spread_or_change(db_session):
    from app.models.external import OilPrice

    db_session.add(OilPrice(series="RBRTE", price_date=date(2026, 10, 10), usd_per_barrel=90.0))
    await db_session.flush()

    (item,) = await brent_price(db_session, _request())

    assert item.content["jet_fuel_crack_spread_usd_per_barrel"] is None
    assert item.content["change_pct_vs_30d_ago"] is None
    assert item.content["avg_30d_usd_per_barrel"] == 90.0


def test_brent_provider_is_wired_into_the_catalog():
    from app.evidence.catalog import EVIDENCE_PROVIDERS
    from app.evidence.reliability import SOURCE_RELIABILITY

    assert EVIDENCE_PROVIDERS["brent_price"] is brent_price
    assert SOURCE_RELIABILITY["eia_brent"] == 0.9

from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.datasets import router
from app.api.deps import get_db
from app.datasets import india_fuel, india_fuel_evidence
from app.datasets.india_fuel import (
    add_months, atf_before, atf_in_effect, atf_prices, crude_basket, india_fuel_basis, metro_for_airport, quarter_months,
    usd_inr_pair,
)
from app.evidence.base import EvidenceRequest
from app.evidence.catalog import EVIDENCE_PROVIDERS
from app.evidence.reliability import SOURCE_RELIABILITY
from app.models.external import (
    AtfPriceIndia, DatasetSnapshot, FuelPrice, FxRate, FxReferenceIndia, IndianCrudeBasket,
)
from app.seed.seed import run_seed
from app.tools.digital_twin_tools import BASELINE_FUEL_USD_PER_GALLON, query_route_profitability
from app.tools.finance_tools import change_exposure, query_financial_exposure

TODAY = date(2026, 10, 16)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(india_fuel, "_today", lambda: TODAY)
    monkeypatch.setattr(india_fuel_evidence, "_today", lambda: TODAY)


def add_atf(db, city, month, inr=None, usd=None, category="domestic"):
    db.add(AtfPriceIndia(city=city, price_month=month, category=category, inr_per_kl=inr, usd_per_kl=usd))


def add_ecb(db, day, rate):
    db.add(FxRate(base="USD", quote="INR", rate_date=day, rate=rate))


async def load_prices(db, *, delhi_now=110000.0, latest_fx=90.0):
    """Delhi 100000 INR/kl since April (so all of 2026-Q3), revised to `delhi_now` in October; ECB USD/INR Q3 mean 90."""
    add_atf(db, "Delhi", date(2026, 4, 1), 100000.0)
    add_atf(db, "Delhi", date(2026, 10, 1), delhi_now)
    for day, rate in ((date(2026, 7, 1), 88.0), (date(2026, 8, 1), 90.0), (date(2026, 9, 1), 92.0), (date(2026, 10, 15), latest_fx)):
        add_ecb(db, day, rate)
    await db.flush()


# --- helpers --------------------------------------------------------------------------------

def test_quarter_months_and_month_arithmetic():
    assert quarter_months("2026-Q3") == [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]
    assert quarter_months("2026-Q1")[0] == date(2026, 1, 1)
    assert add_months(date(2026, 1, 1), -2) == date(2025, 11, 1)
    assert add_months(date(2026, 11, 1), 2) == date(2027, 1, 1)


def test_metro_for_airport():
    assert metro_for_airport("del") == ("Delhi", "origin")
    assert metro_for_airport("MAA") == ("Chennai", "origin")
    assert metro_for_airport("BLR") == ("Chennai", "nearest_metro")
    assert metro_for_airport("HYD") == ("Chennai", "nearest_metro")
    assert metro_for_airport("XYZ") == ("Delhi", "default_delhi")
    assert metro_for_airport("") == ("Delhi", "default_delhi")


async def test_atf_in_effect_carries_the_last_revision_forward(db_session):
    add_atf(db_session, "Mumbai", date(2026, 4, 1), 98247.0)
    add_atf(db_session, "Mumbai", date(2026, 4, 1), usd=1690.33, category="international")
    await db_session.flush()
    assert (await atf_in_effect(db_session, "Mumbai", date(2026, 9, 1))).inr_per_kl == 98247.0
    assert await atf_in_effect(db_session, "Mumbai", date(2026, 3, 1)) is None
    assert (await atf_in_effect(db_session, "Mumbai", date(2026, 9, 1), "international")).usd_per_kl == 1690.33
    assert await atf_before(db_session, "Mumbai", date(2026, 4, 1)) is None


async def test_usd_inr_pair_prefers_fbil_when_it_has_baseline_rates(db_session):
    months = quarter_months("2026-Q3")
    assert await usd_inr_pair(db_session, months) is None
    add_ecb(db_session, date(2026, 8, 1), 90.0)
    add_ecb(db_session, date(2026, 10, 14), 95.0)
    await db_session.flush()
    pair = await usd_inr_pair(db_session, months)
    assert pair == {"source": "fx", "rate": 95.0, "date": date(2026, 10, 14), "baseline_rate": 90.0, "baseline_is_latest": False}

    db_session.add(FxReferenceIndia(rate_date=date(2026, 10, 9), inr_per_usd=96.6149))
    await db_session.flush()
    pair = await usd_inr_pair(db_session, months)  # FBIL has no Q3 rates yet: ECB still gives both
    assert pair["source"] == "fx"

    db_session.add(FxReferenceIndia(rate_date=date(2026, 8, 5), inr_per_usd=91.0))
    await db_session.flush()
    pair = await usd_inr_pair(db_session, months)
    assert pair == {"source": "fbil_fx", "rate": 96.6149, "date": date(2026, 10, 9), "baseline_rate": 91.0, "baseline_is_latest": False}


async def test_usd_inr_pair_falls_back_to_the_latest_rate_as_baseline(db_session):
    db_session.add(FxReferenceIndia(rate_date=date(2026, 10, 9), inr_per_usd=96.0))
    await db_session.flush()
    pair = await usd_inr_pair(db_session, quarter_months("2026-Q3"))
    assert pair == {"source": "fbil_fx", "rate": 96.0, "date": date(2026, 10, 9), "baseline_rate": 96.0, "baseline_is_latest": True}


async def test_basis_exact_numbers(db_session):
    await load_prices(db_session)
    basis = await india_fuel_basis(db_session, "DEL")
    assert basis["source"] == "iocl_atf" and basis["city"] == "Delhi" and basis["city_match"] == "origin"
    assert basis["price_month"] == "2026-10-01" and basis["inr_per_kl"] == 110000.0
    assert basis["baseline_inr_per_kl"] == 100000.0 and basis["baseline_usd_inr"] == 90.0 and basis["usd_inr"] == 90.0
    assert basis["price_ratio"] == pytest.approx(1.1)
    assert basis["usd_per_gallon"] == round(110000 / 90 / 264.172052, 4)
    assert basis["baseline_usd_per_gallon"] == round(100000 / 90 / 264.172052, 4)


async def test_basis_is_none_without_complete_data(db_session):
    assert await india_fuel_basis(db_session, "DEL") is None  # nothing stored
    add_atf(db_session, "Delhi", date(2026, 8, 1), 100000.0)  # starts after July: baseline incomplete
    add_ecb(db_session, date(2026, 10, 1), 90.0)
    await db_session.flush()
    assert await india_fuel_basis(db_session, "DEL") is None
    add_atf(db_session, "Delhi", date(2026, 6, 1), 99000.0)
    await db_session.flush()
    assert (await india_fuel_basis(db_session, "DEL"))["baseline_inr_per_kl"] == pytest.approx(99666.67)
    assert await india_fuel_basis(db_session, "BOM") is None  # no Mumbai ATF
    # international-only rows (no INR price) do not count
    add_atf(db_session, "Mumbai", date(2026, 4, 1), usd=1690.0, category="international")
    await db_session.flush()
    assert await india_fuel_basis(db_session, "BOM") is None


async def test_basis_is_none_without_an_fx_rate(db_session):
    add_atf(db_session, "Delhi", date(2026, 4, 1), 100000.0)
    await db_session.flush()
    assert await india_fuel_basis(db_session, "DEL") is None


async def test_basis_ignores_atf_rows_whose_inr_price_is_missing(db_session):
    add_atf(db_session, "Delhi", date(2026, 4, 1), None, usd=1.0)
    add_ecb(db_session, date(2026, 10, 1), 90.0)
    await db_session.flush()
    assert await india_fuel_basis(db_session, "DEL") is None


# --- route profitability: both fuel paths ------------------------------------------------------

async def _routes(db):
    return {r["route"]: r for r in (await query_route_profitability(db))["routes"]}


async def test_profitability_uses_the_indian_atf_when_present(db_session):
    await run_seed(db_session)
    seed_cost = {r["route"]: r["operating_cost_per_flight_usd"] for r in (await _routes(db_session)).values()}
    await load_prices(db_session)
    db_session.add(FuelPrice(series="X", price_date=date(2026, 10, 1), usd_per_gallon=9.0))  # EIA must be ignored
    await db_session.flush()

    routes = await _routes(db_session)
    del_bom = routes["DEL-BOM"]
    assert del_bom["fuel_price_source"] == "iocl_atf"
    assert del_bom["fuel_cost_factor"] == 1.035  # 1 + 0.35 * (1.1 - 1)
    assert del_bom["fuel_price_usd_per_gallon"] == round(BASELINE_FUEL_USD_PER_GALLON * 1.1, 4) == 2.42
    assert del_bom["operating_cost_per_flight_usd"] == round(seed_cost["DEL-BOM"] * 1.035, 2)
    assert del_bom["atf"]["city"] == "Delhi" and del_bom["atf"]["inr_per_kl"] == 110000.0
    assert "264.172" in del_bom["fuel_price_basis"] and "INR" in del_bom["fuel_price_basis"]
    # BOM, BLR, MAA origins have no ATF price here: they fall back to the EIA price per route
    assert routes["BOM-DEL"]["fuel_price_source"] == "eia_jet_fuel"
    assert routes["BOM-DEL"]["atf"] is None and routes["BOM-DEL"]["fuel_price_usd_per_gallon"] == 9.0


async def test_profitability_factor_follows_the_rupee(db_session):
    await run_seed(db_session)
    await load_prices(db_session, delhi_now=100000.0, latest_fx=99.0)  # price flat in INR, rupee weaker
    del_bom = (await _routes(db_session))["DEL-BOM"]
    ratio = 90 / 99
    assert del_bom["fuel_cost_factor"] == round(1 + 0.35 * (ratio - 1), 6) == 0.968182
    assert del_bom["fuel_price_usd_per_gallon"] == round(2.2 * ratio, 4) == 2.0


async def test_profitability_at_the_baseline_price_leaves_the_seed_costs_unchanged(db_session):
    await run_seed(db_session)
    seed_cost = (await _routes(db_session))["DEL-BOM"]["operating_cost_per_flight_usd"]
    await load_prices(db_session, delhi_now=100000.0)
    del_bom = (await _routes(db_session))["DEL-BOM"]
    assert del_bom["fuel_cost_factor"] == 1.0 and del_bom["operating_cost_per_flight_usd"] == seed_cost


async def test_profitability_falls_back_to_eia_and_to_nothing(db_session):
    await run_seed(db_session)
    none = (await _routes(db_session))["DEL-BOM"]
    assert none["fuel_price_source"] == "none" and none["fuel_cost_factor"] == 1.0 and none["atf"] is None
    db_session.add(FuelPrice(series="X", price_date=date(2026, 10, 1), usd_per_gallon=2.42))
    await db_session.flush()
    eia = (await _routes(db_session))["DEL-BOM"]
    assert eia["fuel_price_source"] == "eia_jet_fuel" and eia["fuel_cost_factor"] == 1.035


# --- finance tool --------------------------------------------------------------------------------

async def test_finance_uses_the_same_basis_and_restates_break_even_in_atf_units(db_session):
    await run_seed(db_session)
    await load_prices(db_session)
    result = (await query_financial_exposure(db_session))["finance"]
    assert "INR per kilolitre" in result["price_basis"] and "USD/gal" in result["price_basis"]
    entry = next(r for r in result["routes"] if r["route"] == "DEL-BOM")
    assert entry["fuel_price_source"] == "iocl_atf" and entry["atf"]["city"] == "Delhi"
    profit = (await _routes(db_session))["DEL-BOM"]
    impact = profit["impact_if_increase_by_one_weekly_flight"]
    inc = entry["increase"]
    f0 = 1.035
    p_star = 2.2 * ((impact["revenue_usd"] * f0 / impact["cost_usd"] - 1) / 0.35 + 1)
    assert inc["break_even_fuel_price_usd_per_gallon"] == pytest.approx(p_star, abs=2e-3)
    ratio = p_star / 2.2
    assert inc["break_even_atf_inr_per_kl"] == pytest.approx(ratio * 100000.0, abs=30)  # FX unchanged since Q3 mean
    assert inc["break_even_atf_usd_per_gallon"] == pytest.approx(ratio * 100000 / 90 / 264.172052, abs=2e-3)
    assert inc["fuel_headroom_pct"] == pytest.approx((p_star - 2.42) / 2.42 * 100, abs=0.1)
    eia_entry = next(r for r in result["routes"] if r["route"] == "BOM-DEL")
    assert eia_entry["fuel_price_source"] == "none"
    assert eia_entry["increase"]["break_even_atf_inr_per_kl"] is None


def test_change_exposure_atf_units_exact():
    atf = {"baseline_inr_per_kl": 100000.0, "baseline_usd_inr": 90.0, "usd_inr": 99.0, "baseline_usd_per_gallon": 4.2}
    out = change_exposure(revenue_usd=10000, weekly_cost_usd=8000, profit_usd=2000, fuel_price=2.2, atf=atf)
    ratio = ((10000 / 8000) - 1) / 0.35 + 1  # break-even price ratio at factor 1.0
    assert out["break_even_atf_inr_per_kl"] == pytest.approx(ratio * 100000 / 90 * 99, abs=1)
    assert out["break_even_atf_usd_per_gallon"] == pytest.approx(ratio * 4.2, abs=1e-3)
    no_break_even = change_exposure(revenue_usd=1000, weekly_cost_usd=8000, profit_usd=-7000, fuel_price=2.2, atf=atf)
    assert no_break_even["break_even_atf_inr_per_kl"] is None and no_break_even["break_even_atf_usd_per_gallon"] is None


# --- queries and API -----------------------------------------------------------------------------

async def test_atf_prices_window_includes_the_opening_revision(db_session):
    add_atf(db_session, "Delhi", date(2025, 1, 1), 90000.0)
    add_atf(db_session, "Delhi", date(2025, 11, 1), 95000.0)
    add_atf(db_session, "Delhi", date(2026, 4, 1), 100000.0)
    add_atf(db_session, "Delhi", date(2026, 4, 1), usd=1690.81, category="international")
    add_atf(db_session, "Mumbai", date(2026, 4, 1), 98247.0)
    await db_session.flush()
    rows = await atf_prices(db_session, "delhi", 12)  # window starts 2025-10-01
    assert [(r.price_month, r.category) for r in rows] == [
        (date(2025, 1, 1), "domestic"), (date(2025, 11, 1), "domestic"), (date(2026, 4, 1), "domestic"),
        (date(2026, 4, 1), "international"),
    ]
    short = await atf_prices(db_session, None, 1)
    assert [(r.city, r.price_month) for r in short if r.category == "domestic"] == [
        ("Delhi", date(2026, 4, 1)), ("Mumbai", date(2026, 4, 1))
    ]
    assert await atf_prices(db_session, "Pune", 12) == []


async def test_crude_basket_window(db_session):
    for month, value in ((date(2025, 9, 1), 69.61), (date(2025, 10, 1), 65.08), (date(2026, 10, 1), 122.01)):
        db_session.add(IndianCrudeBasket(price_month=month, usd_per_bbl=value))
    await db_session.flush()
    assert [b.usd_per_bbl for b in await crude_basket(db_session, 12)] == [65.08, 122.01]
    assert [b.usd_per_bbl for b in await crude_basket(db_session, 1)] == [122.01]


def _client(db_session) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_api_atf_india(db_session):
    async with _client(db_session) as client:
        assert (await client.get("/api/datasets/atf-india")).json() == []
    add_atf(db_session, "Delhi", date(2026, 4, 1), 104927.0)
    add_atf(db_session, "Delhi", date(2026, 4, 1), usd=1690.81, category="international")
    add_atf(db_session, "Chennai", date(2026, 4, 1), 109873.0)
    await db_session.flush()
    async with _client(db_session) as client:
        body = (await client.get("/api/datasets/atf-india", params={"city": "DELHI", "months": 24})).json()
        assert body == [
            {"city": "Delhi", "price_month": "2026-04-01", "category": "domestic", "inr_per_kl": 104927.0, "usd_per_kl": None},
            {"city": "Delhi", "price_month": "2026-04-01", "category": "international", "inr_per_kl": None, "usd_per_kl": 1690.81},
        ]
        assert len((await client.get("/api/datasets/atf-india")).json()) == 3
        assert (await client.get("/api/datasets/atf-india", params={"months": 0})).status_code == 422
        assert (await client.get("/api/datasets/atf-india", params={"months": 121})).status_code == 422


async def test_api_crude_basket(db_session):
    db_session.add_all([
        IndianCrudeBasket(price_month=date(2026, 9, 1), usd_per_bbl=116.09),
        IndianCrudeBasket(price_month=date(2026, 10, 1), usd_per_bbl=122.01),
    ])
    await db_session.flush()
    async with _client(db_session) as client:
        body = (await client.get("/api/datasets/crude-basket", params={"months": 6})).json()
        assert body == [{"price_month": "2026-09-01", "usd_per_bbl": 116.09}, {"price_month": "2026-10-01", "usd_per_bbl": 122.01}]
        assert (await client.get("/api/datasets/crude-basket", params={"months": 0})).status_code == 422
        assert len((await client.get("/api/datasets/crude-basket")).json()) == 2


# --- evidence providers ----------------------------------------------------------------------------

def test_providers_are_registered_with_reliability():
    assert EVIDENCE_PROVIDERS["atf_india"] is india_fuel_evidence.atf_india
    assert EVIDENCE_PROVIDERS["crude_basket_india"] is india_fuel_evidence.crude_basket_india
    assert SOURCE_RELIABILITY["iocl"] == 0.95 and SOURCE_RELIABILITY["ppac"] == 0.9


async def test_atf_provider_without_data(db_session):
    assert await india_fuel_evidence.atf_india(db_session, EvidenceRequest("NETWORK", "x", "DEL-BOM")) == []


async def test_atf_provider_reports_changes(db_session):
    add_atf(db_session, "Mumbai", date(2025, 4, 1), 90000.0)
    add_atf(db_session, "Mumbai", date(2026, 4, 1), 99000.0)
    add_atf(db_session, "Mumbai", date(2026, 4, 1), usd=1690.33, category="international")
    add_atf(db_session, "Mumbai", date(2026, 10, 1), 108900.0)
    snapshot = DatasetSnapshot(
        source="iocl_atf", fetched_at=datetime(2026, 10, 16, tzinfo=timezone.utc), status="SUCCESS", source_url="u",
        row_count=1, details={"via": "wayback"},
    )
    db_session.add(snapshot)
    await db_session.flush()
    (item,) = await india_fuel_evidence.atf_india(db_session, EvidenceRequest("NETWORK", "x", "BOM-DEL"))
    assert item.id == "atf:iocl:Mumbai:2026-10-01" and item.source == "iocl" and item.reliability == 0.95
    assert item.fetched_at == snapshot.fetched_at and item.url == "https://iocl.com/prices-of-petroleum-products"
    assert item.content["city"] == "Mumbai" and item.content["origin_airport"] == "BOM"
    assert item.content["inr_per_kl"] == 108900.0
    assert item.content["previous_price_month"] == "2026-04-01" and item.content["change_pct_vs_previous_month"] == 10.0
    assert item.content["year_ago_price_month"] == "2025-04-01"
    assert item.content["change_pct_vs_year_ago"] == 21.0  # 108900 / 90000
    assert item.content["international_run_usd_per_kl"] == 1690.33
    assert item.content["data_via"] == "wayback" and item.content["city_match"] == "origin"


async def test_atf_provider_nearest_metro_default_and_missing_history(db_session):
    add_atf(db_session, "Chennai", date(2026, 4, 1), 109873.0)
    add_atf(db_session, "Delhi", date(2026, 4, 1), 104927.0)
    await db_session.flush()
    (blr,) = await india_fuel_evidence.atf_india(db_session, EvidenceRequest("FLEET", "x", "BLR-HYD"))
    assert blr.content["city"] == "Chennai" and blr.content["city_match"] == "nearest_metro"
    assert blr.content["change_pct_vs_previous_month"] is None and blr.content["change_pct_vs_year_ago"] is None
    assert blr.content["previous_price_month"] is None and blr.content["year_ago_price_month"] is None
    assert blr.content["international_run_usd_per_kl"] is None and blr.content["data_via"] is None and blr.fetched_at is None
    (none_route,) = await india_fuel_evidence.atf_india(db_session, EvidenceRequest("FINANCE", "x", None))
    assert none_route.content["city"] == "Delhi" and none_route.content["city_match"] == "default_delhi"
    assert none_route.content["origin_airport"] is None


async def test_crude_provider(db_session):
    assert await india_fuel_evidence.crude_basket_india(db_session, EvidenceRequest("FINANCE", "x", None)) == []
    for month, value in ((date(2025, 10, 1), 65.08), (date(2026, 8, 1), 90.19), (date(2026, 9, 1), 116.09), (date(2026, 10, 1), 122.01)):
        db_session.add(IndianCrudeBasket(price_month=month, usd_per_bbl=value))
    db_session.add(DatasetSnapshot(
        source="ppac_crude_basket", fetched_at=datetime(2026, 10, 16, tzinfo=timezone.utc), status="SUCCESS",
        source_url="u", row_count=4, details={},
    ))
    await db_session.flush()
    (item,) = await india_fuel_evidence.crude_basket_india(db_session, EvidenceRequest("FINANCE", "x", None))
    assert item.id == "crude:ppac:2026-10-01" and item.source == "ppac" and item.reliability == 0.9
    assert item.content["usd_per_bbl"] == 122.01
    assert item.content["avg_3m_usd_per_bbl"] == round((90.19 + 116.09 + 122.01) / 3, 2)
    assert item.content["change_pct_vs_previous_month"] == round((122.01 / 116.09 - 1) * 100, 2)
    assert item.content["change_pct_vs_year_ago"] == round((122.01 / 65.08 - 1) * 100, 2)
    assert item.fetched_at is not None


async def test_crude_provider_without_history(db_session):
    db_session.add(IndianCrudeBasket(price_month=date(2026, 10, 1), usd_per_bbl=122.01))
    await db_session.flush()
    (item,) = await india_fuel_evidence.crude_basket_india(db_session, EvidenceRequest("FINANCE", "x", None))
    assert item.content["avg_3m_usd_per_bbl"] == 122.01 and item.content["change_pct_vs_previous_month"] is None
    assert item.fetched_at is None

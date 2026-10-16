from datetime import date, timedelta

import pytest
from sqlalchemy import update

from app.models.digital_twin import Route
from app.models.external import FuelPrice, FxRate
from app.seed.seed import run_seed
from app.tools.digital_twin_tools import query_route_profitability
from app.tools.finance_tools import (
    FUEL_SHOCK_PCT, HIGH_RISK_HEADROOM_PCT, INR_SHOCK_PCT, MODERATE_RISK_HEADROOM_PCT,
    change_exposure, classify_financial_risk, query_financial_exposure,
)

SERIES = "EER_EPJK_PF4_RGC_DPG"
DAY = date(2026, 10, 1)


def test_constants():
    assert (FUEL_SHOCK_PCT, INR_SHOCK_PCT) == (10, 5)
    assert (HIGH_RISK_HEADROOM_PCT, MODERATE_RISK_HEADROOM_PCT) == (10, 25)


# Worked example at the baseline price 2.20 (factor 1.0): weekly revenue 10,000, weekly cost 8,000, profit 2,000.
#   cost(P) = 8000 * (1 + 0.35 (P/2.2 - 1));  zero profit when the factor is 10000/8000 = 1.25
#   => P* = 2.2 * ((1.25 - 1) / 0.35 + 1) = 2.2 * 12/7 = 3.771429; headroom = (P* - 2.2)/2.2 = 71.43%
#   fuel +10% (2.42): factor 1.035, cost 8280 => profit change -280
#   INR 5% weaker: revenue 10000 / 1.05 = 9523.81 => profit change -476.19
def test_change_exposure_worked_example():
    out = change_exposure(revenue_usd=10000, weekly_cost_usd=8000, profit_usd=2000, fuel_price=2.2)
    assert out["profit_usd"] == 2000
    assert out["break_even_fuel_price_usd_per_gallon"] == pytest.approx(3.7714, abs=1e-4)
    assert out["fuel_headroom_pct"] == pytest.approx(71.43, abs=1e-2)
    assert out["profit_change_if_fuel_up_10pct_usd"] == pytest.approx(-280.0, abs=1e-6)
    assert out["profit_change_if_inr_weakens_5pct_usd"] == pytest.approx(-476.19, abs=1e-2)
    assert out["financial_risk"] == "LOW"


def test_change_exposure_scales_cost_with_current_price():
    # At 2.42 the factor is 1.035, so the weekly cost 8280 already includes it. Revenue 10000:
    # f* = 10000 * 1.035 / 8280 = 1.25 again => same break-even price 3.7714; headroom (3.7714-2.42)/2.42 = 55.84%
    out = change_exposure(revenue_usd=10000, weekly_cost_usd=8280, profit_usd=1720, fuel_price=2.42)
    assert out["break_even_fuel_price_usd_per_gallon"] == pytest.approx(3.7714, abs=1e-4)
    assert out["fuel_headroom_pct"] == pytest.approx(55.84, abs=1e-2)
    # +10% -> 2.662, factor 1.0735; cost 8280 * 1.0735 / 1.035 = 8588 => change -308
    assert out["profit_change_if_fuel_up_10pct_usd"] == pytest.approx(-308.0, abs=1e-6)


def test_change_exposure_small_positive_headroom_and_loss_making_change():
    # revenue 8100, cost 8000 at 2.2: f* = 1.0125 -> P* = 2.2 * (0.0125/0.35 + 1) = 2.2786 (+3.57%) => HIGH
    out = change_exposure(revenue_usd=8100, weekly_cost_usd=8000, profit_usd=100, fuel_price=2.2)
    assert out["break_even_fuel_price_usd_per_gallon"] == pytest.approx(2.2786, abs=1e-4)
    assert out["fuel_headroom_pct"] == pytest.approx(3.57, abs=1e-2)
    assert out["financial_risk"] == "HIGH"
    # unprofitable now: revenue 7900 -> P* = 2.2 * (-0.0125/0.35 + 1) = 2.1214 (-3.57%)
    loss = change_exposure(revenue_usd=7900, weekly_cost_usd=8000, profit_usd=-100, fuel_price=2.2)
    assert loss["break_even_fuel_price_usd_per_gallon"] == pytest.approx(2.1214, abs=1e-4)
    assert loss["fuel_headroom_pct"] == pytest.approx(-3.57, abs=1e-2)
    assert loss["financial_risk"] == "HIGH"


def test_change_exposure_decrease_has_negative_revenue_and_cost():
    # Removing a flight: revenue lost -6000, cost saved -8000 (profit +2000).
    # f* = -6000 / -8000 = 0.75 -> P* = 2.2 * (-0.25/0.35 + 1) = 0.6286
    out = change_exposure(revenue_usd=-6000, weekly_cost_usd=-8000, profit_usd=2000, fuel_price=2.2)
    assert out["break_even_fuel_price_usd_per_gallon"] == pytest.approx(0.6286, abs=1e-4)
    assert out["fuel_headroom_pct"] == pytest.approx(-71.43, abs=1e-2)
    assert out["profit_change_if_fuel_up_10pct_usd"] == pytest.approx(280.0, abs=1e-6)  # saves more fuel
    assert out["profit_change_if_inr_weakens_5pct_usd"] == pytest.approx(285.71, abs=1e-2)  # loses less revenue
    assert out["financial_risk"] == "LOW"


def test_change_exposure_no_break_even_when_cost_is_zero():
    out = change_exposure(revenue_usd=500, weekly_cost_usd=0, profit_usd=500, fuel_price=2.2)
    assert out["break_even_fuel_price_usd_per_gallon"] is None
    assert out["fuel_headroom_pct"] is None
    assert out["profit_change_if_fuel_up_10pct_usd"] == 0
    assert out["financial_risk"] == "LOW"  # fuel can never make it unprofitable


def test_change_exposure_no_positive_break_even_price():
    # revenue 1000 vs cost 8000: f* = 0.125 -> P* = 2.2 * (-0.875/0.35 + 1) < 0 => no positive break-even
    out = change_exposure(revenue_usd=1000, weekly_cost_usd=8000, profit_usd=-7000, fuel_price=2.2)
    assert out["break_even_fuel_price_usd_per_gallon"] is None
    assert out["fuel_headroom_pct"] is None
    assert out["financial_risk"] == "HIGH"  # unprofitable now


def test_change_exposure_without_fuel_price():
    out = change_exposure(revenue_usd=10000, weekly_cost_usd=8000, profit_usd=2000, fuel_price=None)
    assert out["break_even_fuel_price_usd_per_gallon"] == pytest.approx(3.7714, abs=1e-4)
    assert out["fuel_headroom_pct"] is None
    assert out["profit_change_if_fuel_up_10pct_usd"] is None
    assert out["financial_risk"] is None
    assert out["profit_change_if_inr_weakens_5pct_usd"] == pytest.approx(-476.19, abs=1e-2)
    loss = change_exposure(revenue_usd=7000, weekly_cost_usd=8000, profit_usd=-1000, fuel_price=None)
    assert loss["financial_risk"] == "HIGH"


@pytest.mark.parametrize(
    "headroom,profit,expected",
    [
        (9.99, 100, "HIGH"), (-9.99, 100, "HIGH"), (10.0, 100, "MODERATE"), (-10.0, 100, "MODERATE"),
        (24.99, 100, "MODERATE"), (25.0, 100, "LOW"), (-60.0, 100, "LOW"), (50.0, 0, "HIGH"),
        (50.0, -1, "HIGH"), (None, 100, "LOW"), (None, -5, "HIGH"),
    ],
)
def test_classify_financial_risk(headroom, profit, expected):
    assert classify_financial_risk(headroom, profit) == expected


# --- the tool against the seeded database ------------------------------------------------------

async def _add_fuel(db, price, day=DAY):
    db.add(FuelPrice(series=SERIES, price_date=day, usd_per_gallon=price))
    await db.commit()


async def _add_fx(db, rate, day=DAY):
    db.add(FxRate(base="USD", quote="INR", rate_date=day, rate=rate))
    await db.commit()


def _route(result, name):
    return next(r for r in result["finance"]["routes"] if r["route"] == name)


async def test_tool_profit_matches_route_profitability(db_session):
    await run_seed(db_session)
    await _add_fuel(db_session, 4.562)
    await _add_fx(db_session, 84.0)
    profit = {r["route"]: r for r in (await query_route_profitability(db_session))["routes"]}
    result = await query_financial_exposure(db_session)
    assert {r["route"] for r in result["finance"]["routes"]} == set(profit)
    for entry in result["finance"]["routes"]:
        assert entry["increase"]["profit_usd"] == profit[entry["route"]]["impact_if_increase_by_one_weekly_flight"]["profit_usd"]
        assert entry["decrease"]["profit_usd"] == profit[entry["route"]]["impact_if_decrease_by_one_weekly_flight"]["profit_usd"]


async def test_tool_hand_computed_del_bom_increase(db_session):
    await run_seed(db_session)
    await _add_fuel(db_session, 4.562)
    inc = _route(await query_financial_exposure(db_session), "DEL-BOM")["increase"]
    base = {r["route"]: r for r in (await query_route_profitability(db_session))["routes"]}["DEL-BOM"]
    impact = base["impact_if_increase_by_one_weekly_flight"]
    f0 = 1 + 0.35 * (4.562 / 2.2 - 1)
    expected_p = 2.2 * ((impact["revenue_usd"] * f0 / impact["cost_usd"] - 1) / 0.35 + 1)
    assert inc["break_even_fuel_price_usd_per_gallon"] == pytest.approx(expected_p, abs=2e-3)
    assert inc["fuel_headroom_pct"] == pytest.approx((expected_p - 4.562) / 4.562 * 100, abs=0.1)
    assert inc["profit_change_if_fuel_up_10pct_usd"] == pytest.approx(
        -impact["cost_usd"] * (0.35 * 0.1 * 4.562 / 2.2) / f0, abs=1.0
    )
    assert inc["profit_change_if_inr_weakens_5pct_usd"] == pytest.approx(-impact["revenue_usd"] * 0.05 / 1.05, abs=0.01)
    assert inc["financial_risk"] in {"LOW", "MODERATE", "HIGH"}


async def test_tool_break_even_is_where_profit_is_zero(db_session):
    """Re-price the fuel at the break-even and the change's profit is ~0."""
    await run_seed(db_session)
    await _add_fuel(db_session, 2.2)
    inc = _route(await query_financial_exposure(db_session), "BOM-DEL")["increase"]
    assert inc["break_even_fuel_price_usd_per_gallon"] is not None
    await _add_fuel(db_session, inc["break_even_fuel_price_usd_per_gallon"], day=DAY + timedelta(days=1))
    repriced = {r["route"]: r for r in (await query_route_profitability(db_session))["routes"]}["BOM-DEL"]
    assert abs(repriced["impact_if_increase_by_one_weekly_flight"]["profit_usd"]) <= 2


async def test_tool_market_context(db_session):
    await run_seed(db_session)
    for offset, price in ((40, 2.0), (20, 3.0), (0, 4.0)):
        await _add_fuel(db_session, price, day=DAY - timedelta(days=offset))
    await _add_fx(db_session, 80.0, day=DAY - timedelta(days=20))
    await _add_fx(db_session, 84.0, day=DAY)
    finance = (await query_financial_exposure(db_session))["finance"]
    market = finance["market"]
    assert market["fuel_usd_per_gallon"] == 4.0
    assert market["fuel_date"] == DAY.isoformat()
    assert market["fuel_avg_30d_usd_per_gallon"] == 3.5  # the 2.0 reading is older than 30 days
    assert market["fuel_change_pct_30d"] == pytest.approx(33.33, abs=1e-2)  # vs the oldest price in the window (3.0)
    assert market["usd_inr"] == 84.0
    assert market["usd_inr_change_pct_30d"] == 5.0
    assert finance["notes"] == []


async def test_tool_without_fuel_or_fx_data_returns_nulls_and_notes(db_session):
    await run_seed(db_session)
    finance = (await query_financial_exposure(db_session))["finance"]
    market = finance["market"]
    assert market["fuel_usd_per_gallon"] is None and market["usd_inr"] is None
    assert market["fuel_avg_30d_usd_per_gallon"] is None and market["fuel_change_pct_30d"] is None
    assert market["usd_inr_change_pct_30d"] is None
    assert len(finance["notes"]) == 2
    inc = _route({"finance": finance}, "BOM-DEL")["increase"]
    assert inc["fuel_headroom_pct"] is None and inc["financial_risk"] is None
    assert inc["profit_change_if_fuel_up_10pct_usd"] is None
    assert inc["profit_change_if_inr_weakens_5pct_usd"] is not None


async def test_tool_single_reading_has_no_30_day_change(db_session):
    await run_seed(db_session)
    await _add_fuel(db_session, 3.0)
    await _add_fx(db_session, 84.0)
    market = (await query_financial_exposure(db_session))["finance"]["market"]
    assert market["fuel_avg_30d_usd_per_gallon"] == 3.0
    assert market["fuel_change_pct_30d"] is None and market["usd_inr_change_pct_30d"] is None


async def test_tool_route_without_economics_has_no_exposure(db_session):
    await run_seed(db_session)
    await db_session.execute(update(Route).values(average_fare_usd=None))
    await db_session.commit()
    result = await query_financial_exposure(db_session)
    assert all(r["increase"] is None and r["decrease"] is None for r in result["finance"]["routes"])


async def test_tool_decrease_to_zero_flights_is_none(db_session):
    await run_seed(db_session)
    await db_session.execute(update(Route).values(current_frequency=1))
    await db_session.commit()
    await _add_fuel(db_session, 2.2)
    entry = _route(await query_financial_exposure(db_session), "BOM-DEL")
    assert entry["decrease"] is None and entry["increase"] is not None


# --- the airport-charge component of each route --------------------------------------------------

async def test_tool_adds_the_airport_charge_component_per_route(db_session):
    from app.datasets import airport_charges

    await run_seed(db_session)
    await airport_charges.fetch_airport_charges(db_session)
    await _add_fuel(db_session, 2.2)
    await _add_fx(db_session, 84.0)

    finance = (await query_financial_exposure(db_session))["finance"]

    # BOM-DEL lands at DEL: 347 (narrow body, Rs/MT) * 78 t (A320) = Rs 27,066; the 1 h stand time is inside the free period
    component = _route({"finance": finance}, "BOM-DEL")["airport_charges"]
    assert component["aircraft_type"] == "A320"
    assert component["per_flight_inr"] == 27066.0 and component["per_flight_usd"] == 322.21  # 27,066 / 84
    assert component["weekly_change_if_one_weekly_flight_added_usd"] == 322.21
    assert component["weekly_change_if_one_weekly_flight_removed_usd"] == -322.21
    assert component["passenger_charges"]["per_passenger_inr"] == 231.0
    assert "operating_cost_per_flight_usd" in component["note"]
    assert finance["airport_charges_info"]["sources"] and finance["airport_charges_info"]["usd_inr"] == 84.0
    # additive: the existing exposure figures are untouched
    assert set(_route({"finance": finance}, "BOM-DEL")) >= {"route", "current_frequency", "increase", "decrease", "airport_charges"}


async def test_tool_without_stored_charges_has_a_null_component_and_unchanged_notes(db_session):
    await run_seed(db_session)
    finance = (await query_financial_exposure(db_session))["finance"]
    assert all(r["airport_charges"] is None for r in finance["routes"])
    assert len(finance["notes"]) == 2  # fuel and FX only: the charge component does not touch the existing notes
    assert any("No airport charges" in n for n in finance["airport_charges_info"]["notes"])

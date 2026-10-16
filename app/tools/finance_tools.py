from statistics import mean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import fx
from app.datasets.evidence import pct_change
from app.datasets.queries import fuel_prices, fx_rates
from app.models.external import FuelPrice, FxRate
from app.tools.digital_twin_tools import (
    BASELINE_FUEL_USD_PER_GALLON, FUEL_COST_SHARE, fuel_cost_factor, query_route_profitability,
)

# Sensitivity shocks, in percent.
FUEL_SHOCK_PCT = 10
INR_SHOCK_PCT = 5
# financial_risk thresholds on |fuel_headroom_pct|: below HIGH_RISK -> HIGH, below MODERATE_RISK -> MODERATE, else LOW.
HIGH_RISK_HEADROOM_PCT = 10
MODERATE_RISK_HEADROOM_PCT = 25
WINDOW_DAYS = 30


def classify_financial_risk(fuel_headroom_pct: float | None, profit_usd: float) -> str:
    """HIGH if the change is unprofitable now or |fuel headroom| < 10%; MODERATE if < 25%; else LOW.

    A missing headroom (no finite positive break-even price) means fuel cannot flip a profitable
    change into a loss, so it is LOW unless the change is already unprofitable.
    """
    if profit_usd <= 0:
        return "HIGH"
    if fuel_headroom_pct is None:
        return "LOW"
    if abs(fuel_headroom_pct) < HIGH_RISK_HEADROOM_PCT:
        return "HIGH"
    if abs(fuel_headroom_pct) < MODERATE_RISK_HEADROOM_PCT:
        return "MODERATE"
    return "LOW"


def change_exposure(*, revenue_usd: float, weekly_cost_usd: float, profit_usd: float, fuel_price: float | None) -> dict:
    """Fuel and USD/INR sensitivity of one frequency change's weekly profit.

    `revenue_usd` and `weekly_cost_usd` are the change's weekly revenue and operating cost at the
    current fuel price `fuel_price` (both negative for a decrease); `profit_usd` is the tool's
    already-rounded profit, passed through unchanged.

    Cost model: cost(P) = cost_now * f(P) / f(P0), with f(P) = 1 + 0.35 * (P / 2.20 - 1).
    - Break-even: profit(P*) = 0  =>  f(P*) = revenue * f(P0) / cost_now  =>
      P* = 2.20 * ((f(P*) - 1) / 0.35 + 1). It does not depend on the current price except through
      f(P0), so it is computable without one; None when cost is 0 or P* is not positive.
    - Fuel headroom % = (P* - P0) / P0 * 100 (None without a price or a break-even).
    - Fuel +10%: profit change = -cost_now * (f(1.1 * P0) / f(P0) - 1).
    - INR weakens 5%: fares are INR-denominated revenue converted at the USD/INR rate while fuel is a
      USD cost, so revenue_usd falls to revenue / 1.05 and profit changes by revenue * (1/1.05 - 1).
      The rate itself cancels out of this ratio, so no FX reading is needed.
    """
    factor_now = fuel_cost_factor(fuel_price)
    break_even = None
    if weekly_cost_usd != 0:
        target_factor = revenue_usd * factor_now / weekly_cost_usd
        candidate = BASELINE_FUEL_USD_PER_GALLON * ((target_factor - 1) / FUEL_COST_SHARE + 1)
        if candidate > 0:
            break_even = candidate

    headroom = None
    fuel_up = None
    risk = None
    if fuel_price is not None:
        if break_even is not None:
            headroom = round((break_even - fuel_price) / fuel_price * 100, 2)
        fuel_up = -weekly_cost_usd * (fuel_cost_factor(fuel_price * (1 + FUEL_SHOCK_PCT / 100)) / factor_now - 1)
        risk = classify_financial_risk(headroom, profit_usd)
    elif profit_usd <= 0:
        risk = "HIGH"

    return {
        "profit_usd": profit_usd,
        "break_even_fuel_price_usd_per_gallon": round(break_even, 4) if break_even is not None else None,
        "fuel_headroom_pct": headroom,
        "profit_change_if_fuel_up_10pct_usd": round(fuel_up, 2) if fuel_up is not None else None,
        "profit_change_if_inr_weakens_5pct_usd": round(revenue_usd * (1 / (1 + INR_SHOCK_PCT / 100) - 1), 2),
        "financial_risk": risk,
    }


async def _market_context(db: AsyncSession) -> tuple[dict, list[str]]:
    notes = []
    market = {
        "fuel_usd_per_gallon": None, "fuel_date": None, "fuel_avg_30d_usd_per_gallon": None, "fuel_change_pct_30d": None,
        "usd_inr": None, "usd_inr_date": None, "usd_inr_change_pct_30d": None,
    }
    latest_fuel = (await db.execute(select(FuelPrice).order_by(FuelPrice.price_date.desc()).limit(1))).scalars().first()
    if latest_fuel is None:
        notes.append("No jet fuel price data is loaded: fuel sensitivities and fuel risk are unavailable.")
    else:
        window = await fuel_prices(db, WINDOW_DAYS, today=latest_fuel.price_date)
        values = [row.usd_per_gallon for row in window]
        market["fuel_usd_per_gallon"] = latest_fuel.usd_per_gallon
        market["fuel_date"] = latest_fuel.price_date.isoformat()
        market["fuel_avg_30d_usd_per_gallon"] = round(mean(values), 4)
        # Change vs the oldest reading inside the 30-day window.
        market["fuel_change_pct_30d"] = pct_change(latest_fuel.usd_per_gallon, values[0]) if len(values) > 1 else None

    latest_fx = (
        await db.execute(
            select(FxRate).where(FxRate.base == fx.BASE, FxRate.quote == fx.QUOTE).order_by(FxRate.rate_date.desc()).limit(1)
        )
    ).scalars().first()
    if latest_fx is None:
        notes.append("No USD/INR exchange rate data is loaded: the exchange-rate context is unavailable.")
    else:
        window = await fx_rates(db, fx.QUOTE, WINDOW_DAYS, today=latest_fx.rate_date)
        rates = [row.rate for row in window]
        market["usd_inr"] = latest_fx.rate
        market["usd_inr_date"] = latest_fx.rate_date.isoformat()
        market["usd_inr_change_pct_30d"] = pct_change(latest_fx.rate, rates[0]) if len(rates) > 1 else None
    return market, notes


async def query_financial_exposure(db: AsyncSession) -> dict:
    """Precomputed fuel and USD/INR exposure of a one-flight increase and decrease on every twin route.

    Reuses query_route_profitability, so each `profit_usd` equals that tool's impact profit. See
    change_exposure for the break-even, headroom and sensitivity formulas and the INR assumption
    (fares INR-denominated, fuel a USD cost). financial_risk thresholds: HIGH if the change is
    unprofitable now or |fuel_headroom_pct| < 10, MODERATE if < 25, else LOW.
    Missing fuel or FX data yields nulls plus an explanatory note, never made-up numbers.
    """
    profitability = await query_route_profitability(db)
    market, notes = await _market_context(db)
    routes = []
    for entry in profitability["routes"]:
        fuel_price = entry["fuel_price_usd_per_gallon"]
        exposure = {"route": entry["route"], "current_frequency": entry["current_frequency"]}
        for key, change in (("increase", 1), ("decrease", -1)):
            impact = entry[f"impact_if_{'increase' if change > 0 else 'decrease'}_by_one_weekly_flight"]
            exposure[key] = (
                None
                if impact is None
                else change_exposure(
                    revenue_usd=impact["revenue_usd"],
                    weekly_cost_usd=change * entry["operating_cost_per_flight_usd"],
                    profit_usd=impact["profit_usd"],
                    fuel_price=fuel_price,
                )
            )
        routes.append(exposure)
    return {"finance": {"market": market, "notes": notes, "routes": routes}}

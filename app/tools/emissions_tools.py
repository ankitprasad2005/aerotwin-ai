"""CO2 impact of a one-flight weekly frequency change, from the ICAO Carbon Emissions Calculator methodology."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.digital_twin_tools import query_route_profitability

# Source of every constant below:
#   ICAO, "ICAO Carbon Emissions Calculator Methodology", Version 13.1, August 2024 (ICEC v13 methodology),
#   https://icec.icao.int/Documents/Methodology%20ICAO%20Carbon%20Emissions%20Calculator_v13_Final.pdf
#
# Section 3, formula legend: "3.16 = constant representing the number of tonnes of CO2 produced by
# burning a tonne of aviation fuel", i.e. 3.16 kg of CO2 per kg of jet fuel.
CO2_KG_PER_KG_FUEL = 3.16
KM_PER_NAUTICAL_MILE = 1.852

# Appendix C "ICAO Fuel Consumption Table": average fuel consumption (kg) by stage length (nm),
# from the ICAO fuel consumption formula; the row for equivalent aircraft code 320 (Airbus A320),
# the distance bands 125 .. 2500 nm that the table publishes for that aircraft. The figures include
# the whole flight (the table is total fuel by stage length, not cruise only).
A320_FUEL_KG_BY_DISTANCE_NM: tuple[tuple[int, int], ...] = (
    (125, 1672),
    (250, 3430),
    (500, 4585),
    (750, 6212),
    (1000, 7772),
    (1500, 10766),
    (2000, 13648),
    (2500, 16452),
)

# Section 4.2 "Trip distance": the great circle distance is corrected "to include the emissions of
# distance flown in excess of the GCD, stacking, traffic and weather-driven corrections":
# +50 km below 550 km, +100 km from 550 km to 5500 km, +125 km above 5500 km.
SHORT_HAUL_BELOW_KM, LONG_HAUL_ABOVE_KM = 550.0, 5500.0
SHORT_CORRECTION_KM, MEDIUM_CORRECTION_KM, LONG_CORRECTION_KM = 50.0, 100.0, 125.0

# Not from ICAO: the emissions agent's stance. Per-passenger CO2 must move by more than this fraction
# (2%) before it counts as better (SUPPORTS) or worse (OPPOSES); smaller moves are noise (NEUTRAL).
PER_PASSENGER_STANCE_THRESHOLD = 0.02

AIRCRAFT_TYPE = "A320"
EMISSIONS_METHODOLOGY_SOURCES = (
    "ICAO Carbon Emissions Calculator Methodology, Version 13.1 (August 2024), "
    "https://icec.icao.int/Documents/Methodology%20ICAO%20Carbon%20Emissions%20Calculator_v13_Final.pdf",
    "CO2 = fuel burned x 3.16 kg CO2 per kg of jet fuel (ICAO methodology, section 3).",
    "Fuel per flight for an A320 (ICAO aircraft code 320) by stage length, interpolated linearly between the bands of "
    "ICAO methodology Appendix C 'ICAO Fuel Consumption Table'; stage length is the great circle distance plus the "
    "section 4.2 correction (+50 km below 550 km, +100 km up to 5500 km, +125 km above).",
)


def flown_distance_km(gcd_km: float) -> float:
    """Great circle distance plus the ICAO section 4.2 correction for extra distance flown."""
    if gcd_km < SHORT_HAUL_BELOW_KM:
        return gcd_km + SHORT_CORRECTION_KM
    if gcd_km <= LONG_HAUL_ABOVE_KM:
        return gcd_km + MEDIUM_CORRECTION_KM
    return gcd_km + LONG_CORRECTION_KM


def fuel_kg_for_distance_nm(distance_nm: float) -> float:
    """Fuel (kg) for an A320 flight of `distance_nm`, linear between the Appendix C bands.

    Below the first band the fuel is proportional to distance (an assumption: the table has no
    shorter band); beyond the last band the last segment's slope is continued.
    """
    table = A320_FUEL_KG_BY_DISTANCE_NM
    first_nm, first_kg = table[0]
    if distance_nm <= first_nm:
        return first_kg * distance_nm / first_nm
    for (lower_nm, lower_kg), (upper_nm, upper_kg) in zip(table, table[1:]):
        if distance_nm <= upper_nm:
            return lower_kg + (upper_kg - lower_kg) * (distance_nm - lower_nm) / (upper_nm - lower_nm)
    (lower_nm, lower_kg), (upper_nm, upper_kg) = table[-2], table[-1]
    return upper_kg + (upper_kg - lower_kg) * (distance_nm - upper_nm) / (upper_nm - lower_nm)


def emissions_stance(per_passenger_before: float, per_passenger_after: float, total_change_tonnes: float) -> str:
    """SUPPORTS, OPPOSES or NEUTRAL for the change.

    SUPPORTS: total weekly CO2 falls, or CO2 per passenger falls by more than PER_PASSENGER_STANCE_THRESHOLD.
    OPPOSES: CO2 per passenger rises by more than the threshold (and total CO2 did not fall).
    NEUTRAL otherwise, including when there are no passengers before or after to compare.
    """
    if total_change_tonnes < 0:
        return "SUPPORTS"
    if per_passenger_before > 0 and per_passenger_after > 0:
        relative_change = (per_passenger_after - per_passenger_before) / per_passenger_before
        if relative_change < -PER_PASSENGER_STANCE_THRESHOLD:
            return "SUPPORTS"
        if relative_change > PER_PASSENGER_STANCE_THRESHOLD:
            return "OPPOSES"
    return "NEUTRAL"


def emissions_change_impact(
    *,
    current_frequency: int,
    seats_per_flight: int,
    historical_load_factor: float,
    projected_load_factor: float,
    co2_kg_per_flight: float,
    change: int,
) -> dict | None:
    """Weekly CO2 (tonnes) and CO2 per passenger (kg) before and after a frequency change of `change` flights.

    Passengers are seats x load factor per flight: the historical load factor today and the projected
    one (from weekly_frequency_change_impact) after the change. Returns None when the change would
    leave the route with no flights.
    """
    new_frequency = current_frequency + change
    if new_frequency <= 0:
        return None

    current_passengers = current_frequency * seats_per_flight * historical_load_factor
    new_passengers = new_frequency * seats_per_flight * projected_load_factor
    current_tonnes = current_frequency * co2_kg_per_flight / 1000
    new_tonnes = new_frequency * co2_kg_per_flight / 1000
    per_passenger_before = current_frequency * co2_kg_per_flight / current_passengers if current_passengers > 0 else 0.0
    per_passenger_after = new_frequency * co2_kg_per_flight / new_passengers if new_passengers > 0 else 0.0
    change_tonnes = new_tonnes - current_tonnes
    return {
        "new_weekly_co2_tonnes": round(new_tonnes, 3),
        "co2_change_tonnes_per_week": round(change_tonnes, 3),
        "co2_per_passenger_kg_before": round(per_passenger_before, 2),
        "co2_per_passenger_kg_after": round(per_passenger_after, 2),
        "emissions_stance": emissions_stance(per_passenger_before, per_passenger_after, change_tonnes),
    }


def _action(impact: dict | None, fuel_kg: float, co2_kg: float) -> dict | None:
    if impact is None:
        return None
    return {"fuel_kg_per_flight": round(fuel_kg, 1), "co2_kg_per_flight": round(co2_kg, 1), **impact}


async def query_route_emissions(db: AsyncSession) -> dict:
    """CO2 per flight, per week and per passenger for every route, now and after one flight more or fewer.

    Economics come from query_route_profitability so passengers and load factors match what the network
    agent saw. Every figure is precomputed here, never left to the LLM.
    """
    results = []
    for route in (await query_route_profitability(db))["routes"]:
        flown_km = flown_distance_km(route["distance_km"])
        fuel_kg = fuel_kg_for_distance_nm(flown_km / KM_PER_NAUTICAL_MILE)
        co2_kg = fuel_kg * CO2_KG_PER_KG_FUEL
        seats, historical_lf = route["seats_per_flight"], route["historical_load_factor"]
        has_load = seats is not None and historical_lf is not None
        current_passengers = route["current_frequency"] * seats * historical_lf if has_load else 0
        actions = {}
        for key, change in (("increase", 1), ("decrease", -1)):
            economics = route[f"impact_if_{key}_by_one_weekly_flight"]
            actions[key] = _action(
                emissions_change_impact(
                    current_frequency=route["current_frequency"],
                    seats_per_flight=seats,
                    historical_load_factor=historical_lf,
                    projected_load_factor=economics["projected_load_factor"],
                    co2_kg_per_flight=co2_kg,
                    change=change,
                )
                if economics is not None
                else None,
                fuel_kg,
                co2_kg,
            )
        results.append(
            {
                "route": route["route"],
                "current_frequency": route["current_frequency"],
                "distance_km": route["distance_km"],
                "flown_distance_km": round(flown_km, 1),
                "aircraft_type": AIRCRAFT_TYPE,
                "seats_per_flight": seats,
                "historical_load_factor": historical_lf,
                "fuel_kg_per_flight": round(fuel_kg, 1),
                "co2_kg_per_flight": round(co2_kg, 1),
                "current_weekly_co2_tonnes": round(route["current_frequency"] * co2_kg / 1000, 3),
                "co2_per_passenger_kg_current": (
                    round(route["current_frequency"] * co2_kg / current_passengers, 2) if current_passengers > 0 else None
                ),
                "impact_if_increase_by_one_weekly_flight": actions["increase"],
                "impact_if_decrease_by_one_weekly_flight": actions["decrease"],
                "methodology_sources": list(EMISSIONS_METHODOLOGY_SOURCES),
            }
        )
    return {"emissions": results}

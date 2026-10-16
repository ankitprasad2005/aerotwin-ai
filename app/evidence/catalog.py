from app.datasets.evidence import (
    airworthiness_directives, brent_price, dgca_market, fuel_price, fx_rate, market_competition, weather_forecast,
    weather_observation, weather_taf,
)
from app.datasets.traffic_evidence import live_air_traffic
from app.datasets.airport_evidence import airport_infrastructure, airport_throughput
from app.datasets.weather_evidence import imd_warnings, india_weather_summary
from app.datasets.market_evidence import india_holidays, world_bank_demand, world_bank_freight
from app.evidence.base import EvidenceProvider
from app.websearch.evidence import web_search

# Every provider an AgentSpec may name in `evidence_providers`.
EVIDENCE_PROVIDERS: dict[str, EvidenceProvider] = {
    "market_competition": market_competition,
    "fuel_price": fuel_price,
    "brent_price": brent_price,
    "fx_rate": fx_rate,
    "dgca_market": dgca_market,
    "web_search": web_search,
    "weather_observation": weather_observation,
    "weather_forecast": weather_forecast,
    "airworthiness_directives": airworthiness_directives,
    "weather_taf": weather_taf,
    "world_bank_demand": world_bank_demand,
    "world_bank_freight": world_bank_freight,
    "india_holidays": india_holidays,
    "live_air_traffic": live_air_traffic,
    "airport_throughput": airport_throughput,
    "airport_infrastructure": airport_infrastructure,
    "india_weather_summary": india_weather_summary,
    "imd_warnings": imd_warnings,
}

from app.datasets.evidence import (
    dgca_market, fuel_price, fx_rate, market_competition, weather_forecast, weather_observation,
)
from app.datasets.market_evidence import india_holidays, world_bank_demand, world_bank_freight
from app.evidence.base import EvidenceProvider
from app.websearch.evidence import web_search

# Every provider an AgentSpec may name in `evidence_providers`.
EVIDENCE_PROVIDERS: dict[str, EvidenceProvider] = {
    "market_competition": market_competition,
    "fuel_price": fuel_price,
    "fx_rate": fx_rate,
    "dgca_market": dgca_market,
    "web_search": web_search,
    "weather_observation": weather_observation,
    "weather_forecast": weather_forecast,
    "world_bank_demand": world_bank_demand,
    "world_bank_freight": world_bank_freight,
    "india_holidays": india_holidays,
}

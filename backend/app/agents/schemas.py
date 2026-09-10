from typing import Literal

from pydantic import BaseModel, Field


class NetworkRecommendation(BaseModel):
    route: str
    action: Literal["INCREASE_FREQUENCY", "DECREASE_FREQUENCY", "MAINTAIN"]
    expected_profit_impact: float
    expected_revenue_impact: float
    expected_cost_impact: float
    confidence: float = Field(ge=0, le=1)
    risks: list[str]
    reasoning: str


class FleetRecommendation(BaseModel):
    route: str
    aircraft_tail_number: str
    assignment_action: Literal["ASSIGN_ADDITIONAL_AIRCRAFT", "REASSIGN", "NO_CHANGE"]
    aircraft_availability: Literal["AVAILABLE", "UNAVAILABLE"]
    expected_cost_impact: float
    confidence: float = Field(ge=0, le=1)
    risks: list[str]
    reasoning: str

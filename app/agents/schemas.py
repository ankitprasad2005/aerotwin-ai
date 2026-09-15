from typing import Literal

from pydantic import BaseModel, Field

# Field descriptions are sent to the LLM inside the structured-output JSON schema, so they double
# as instructions for what each number means. Money figures are weekly USD, matching
# Route.current_frequency (flights per week) and query_route_profitability's precomputed impacts.


class NetworkRecommendation(BaseModel):
    route: str = Field(description="Route code exactly as given in the route data, e.g. BOM-DEL.")
    action: Literal["INCREASE_FREQUENCY", "DECREASE_FREQUENCY", "MAINTAIN"] = Field(
        description="Change the route's frequency by one weekly flight, or MAINTAIN it."
    )
    expected_profit_impact: float = Field(
        description="Weekly profit change in USD: expected_revenue_impact minus expected_cost_impact."
    )
    expected_revenue_impact: float = Field(
        description="Weekly revenue change in USD, taken from the route's precomputed impact for this action; 0 for MAINTAIN."
    )
    expected_cost_impact: float = Field(
        description=(
            "Weekly operating cost change in USD (negative when flights are removed), taken from the "
            "route's precomputed impact for this action; 0 for MAINTAIN."
        )
    )
    confidence: float = Field(ge=0, le=1)
    risks: list[str]
    reasoning: str


class FleetRecommendation(BaseModel):
    route: str = Field(description="The route the network agent chose, e.g. BOM-DEL.")
    aircraft_tail_number: str
    assignment_action: Literal["ASSIGN_ADDITIONAL_AIRCRAFT", "REASSIGN", "NO_CHANGE"]
    aircraft_availability: Literal["AVAILABLE", "UNAVAILABLE"]
    expected_cost_impact: float = Field(
        description=(
            "Extra weekly cost in USD of making this aircraft available for the route, such as repositioning "
            "it from another airport. Excludes the route's operating cost, which the network agent already "
            "counts. 0 if the aircraft is already at the route's origin or no assignment change is needed."
        )
    )
    confidence: float = Field(ge=0, le=1)
    risks: list[str]
    reasoning: str

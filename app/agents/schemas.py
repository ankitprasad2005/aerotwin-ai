from typing import Literal

from pydantic import BaseModel, Field

CITED_SOURCES_DESCRIPTION = (
    "The ids of the context.evidence items you relied on, exactly as given; an empty list if you used none."
)

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
    cited_sources: list[str] = Field(description=CITED_SOURCES_DESCRIPTION)


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
    cited_sources: list[str] = Field(description=CITED_SOURCES_DESCRIPTION)


class MaintenanceAction(BaseModel):
    tail_number: str = Field(description="Tail number exactly as given in the maintenance data.")
    action: Literal["SCHEDULE_CHECK", "MONITOR", "KEEP_GROUNDED", "RELEASE"]
    reason: str


class MaintenanceRecommendation(BaseModel):
    grounded_aircraft: list[str] = Field(
        description="Tail numbers whose airworthiness is GROUNDED in the maintenance data; they must not be assigned to any flight."
    )
    at_risk_aircraft: list[str] = Field(
        description="Tail numbers whose airworthiness is DUE_SOON; avoid assigning them when an alternative exists."
    )
    actions: list[MaintenanceAction] = Field(
        description="One action for each aircraft that is not SERVICEABLE; empty if every aircraft is SERVICEABLE."
    )
    confidence: float = Field(ge=0, le=1)
    risks: list[str]
    reasoning: str
    cited_sources: list[str] = Field(description=CITED_SOURCES_DESCRIPTION)


class CrewRecommendation(BaseModel):
    route: str = Field(description="The route the network agent chose, e.g. BOM-DEL.")
    crew_availability: Literal["SUFFICIENT", "INSUFFICIENT"] = Field(
        description="SUFFICIENT if the route's crew need can be met, INSUFFICIENT if no qualified crew can cover it."
    )
    assignment_action: Literal["ASSIGN_ADDITIONAL_CREW", "REPOSITION_CREW", "NO_CHANGE"]
    assigned_crew: list[str] = Field(
        description="Employee codes of the crew members assigned, exactly as given in the crew data; empty for NO_CHANGE or INSUFFICIENT."
    )
    expected_cost_impact: float = Field(
        description=(
            "Extra weekly cost in USD of making this crew available for the route, such as repositioning them from "
            "another base. Excludes the route's operating cost, which already includes crew and which the network "
            "agent counts. 0 if the crew is already at the route's origin or no assignment change is needed."
        )
    )
    confidence: float = Field(ge=0, le=1)
    risks: list[str]
    reasoning: str
    cited_sources: list[str] = Field(description=CITED_SOURCES_DESCRIPTION)


class CargoRecommendation(BaseModel):
    route: str = Field(description="The route the network agent chose, e.g. BOM-DEL.")
    cargo_stance: Literal["SUPPORTS", "NEUTRAL", "OPPOSES"] = Field(
        description=(
            "SUPPORTS if the network agent's action raises weekly cargo profit, OPPOSES if it lowers it, "
            "NEUTRAL if cargo profit does not change (including MAINTAIN)."
        )
    )
    expected_revenue_impact: float = Field(
        description=(
            "Weekly cargo revenue change in USD, taken from the route's precomputed impact for the network "
            "agent's action; 0 for MAINTAIN."
        )
    )
    expected_cost_impact: float = Field(
        description=(
            "Weekly cargo handling cost change in USD (negative when cargo is lost), taken from the same "
            "precomputed impact; 0 for MAINTAIN. Excludes the flying cost, which the network agent counts."
        )
    )
    confidence: float = Field(ge=0, le=1)
    risks: list[str]
    reasoning: str
    cited_sources: list[str] = Field(description=CITED_SOURCES_DESCRIPTION)


class EmissionsRecommendation(BaseModel):
    route: str = Field(description="The route the network agent chose, e.g. BOM-DEL.")
    co2_change_tonnes_per_week: float = Field(
        description=(
            "Change in the route's weekly CO2 in tonnes, copied from the route's precomputed co2_change_tonnes_per_week "
            "for the NETWORK entry's route and action (positive when CO2 rises, negative when it falls); 0 for MAINTAIN."
        )
    )
    co2_per_passenger_kg_before: float = Field(
        description=(
            "CO2 per passenger in kg today, copied from the precomputed co2_per_passenger_kg_before for the NETWORK "
            "entry's route and action; for MAINTAIN copy co2_per_passenger_kg_current."
        )
    )
    co2_per_passenger_kg_after: float = Field(
        description=(
            "CO2 per passenger in kg after the change, copied from the precomputed co2_per_passenger_kg_after for the "
            "NETWORK entry's route and action; for MAINTAIN it equals co2_per_passenger_kg_before (unchanged)."
        )
    )
    emissions_stance: Literal["SUPPORTS", "NEUTRAL", "OPPOSES"] = Field(
        description=(
            "Copied from the precomputed emissions_stance for the NETWORK entry's route and action: SUPPORTS if the change "
            "lowers CO2 per passenger by more than 2% or lowers total weekly CO2, OPPOSES if it raises CO2 per passenger "
            "by more than 2%, NEUTRAL otherwise (including MAINTAIN)."
        )
    )
    confidence: float = Field(ge=0, le=1)
    risks: list[str]
    reasoning: str
    cited_sources: list[str] = Field(description=CITED_SOURCES_DESCRIPTION)

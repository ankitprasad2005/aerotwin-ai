"""EMISSIONS agent: schema, spec, search template and its place in the decision engine."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.agents.emissions_agent import EMISSIONS_AGENT_SPEC
from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.registry import AGENT_REGISTRY
from app.agents.schemas import CITED_SOURCES_DESCRIPTION, EmissionsRecommendation
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.evidence.base import EvidenceRequest
from app.seed.seed import run_seed
from app.websearch.evidence import TEMPLATES, build_query
from tests.test_decision_reconcile_all import _all, _maintenance, _run, _vr


def _emissions(**o):
    base = dict(
        route="BOM-DEL", co2_change_tonnes_per_week=18.086, co2_per_passenger_kg_before=124.05,
        co2_per_passenger_kg_after=111.64, emissions_stance="SUPPORTS", confidence=0.85,
        risks=["load factor may not reach 90%"], reasoning="CO2 per passenger falls 10%.", cited_sources=[],
    )
    base.update(o)
    return EmissionsRecommendation(**base)


# --- schema -----------------------------------------------------------------------------------

def test_schema_has_exactly_the_contract_fields():
    assert list(EmissionsRecommendation.model_fields) == [
        "route", "co2_change_tonnes_per_week", "co2_per_passenger_kg_before", "co2_per_passenger_kg_after",
        "emissions_stance", "confidence", "risks", "reasoning", "cited_sources",
    ]


def test_round_trip_and_negative_change():
    rec = _emissions(co2_change_tonnes_per_week=-18.086, emissions_stance="SUPPORTS")
    assert rec.model_dump()["co2_change_tonnes_per_week"] == -18.086


@pytest.mark.parametrize("field, value", [("emissions_stance", "LOVES"), ("confidence", -0.1), ("confidence", 1.1)])
def test_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        _emissions(**{field: value})


@pytest.mark.parametrize("missing", list(EmissionsRecommendation.model_fields))
def test_requires_every_field(missing):
    fields = _emissions().model_dump()
    del fields[missing]
    with pytest.raises(ValidationError):
        EmissionsRecommendation(**fields)


def test_field_descriptions_tell_the_model_to_copy_the_precomputed_values():
    fields = EmissionsRecommendation.model_fields
    for name in ("co2_change_tonnes_per_week", "co2_per_passenger_kg_before", "co2_per_passenger_kg_after"):
        assert "NETWORK" in fields[name].description and "MAINTAIN" in fields[name].description
    assert fields["cited_sources"].description == CITED_SOURCES_DESCRIPTION


# --- spec -------------------------------------------------------------------------------------

def test_spec_shape():
    assert EMISSIONS_AGENT_SPEC.agent_type == "EMISSIONS"
    assert EMISSIONS_AGENT_SPEC.tool_name == "query_route_emissions"
    assert EMISSIONS_AGENT_SPEC.output_schema is EmissionsRecommendation
    assert EMISSIONS_AGENT_SPEC.entities_key == "emissions"
    assert EMISSIONS_AGENT_SPEC.depends_on == ("NETWORK",)
    assert EMISSIONS_AGENT_SPEC.evidence_providers == ("web_search",)
    assert EMISSIONS_AGENT_SPEC.task_description == AGENT_TASKS["EMISSIONS"]
    assert EMISSIONS_AGENT_SPEC.tool_name == AGENT_TOOLS["EMISSIONS"][0]
    assert AGENT_REGISTRY["EMISSIONS"] is EMISSIONS_AGENT_SPEC


def test_instructions_cover_the_network_route_the_precomputed_figures_and_the_guidance():
    text = EMISSIONS_AGENT_SPEC.system_instructions
    for phrase in ("NETWORK", "impact_if_increase_by_one_weekly_flight", "impact_if_decrease_by_one_weekly_flight",
                   "emissions_stance", "MAINTAIN", "methodology_sources", "Never estimate"):
        assert phrase in text
    assert text.endswith(EVIDENCE_GUIDANCE)


async def test_spec_tool_fn_runs_against_seeded_db(db_session):
    await run_seed(db_session)
    result = await EMISSIONS_AGENT_SPEC.tool_fn(db_session)
    assert any(e["route"] == "BOM-DEL" for e in result["emissions"])


# --- web search template ----------------------------------------------------------------------

def test_emissions_search_template():
    assert TEMPLATES["EMISSIONS"] == "India aviation carbon emissions policy {year}"
    request = EvidenceRequest(agent_type="EMISSIONS", objective="o", route="BOM-DEL", previous_results=[])
    now = datetime(2027, 3, 1, tzinfo=timezone.utc)
    assert build_query(request, now=now) == "India aviation carbon emissions policy 2027"


# --- decision engine --------------------------------------------------------------------------

def _with_emissions(**o):
    return _all(MAINTENANCE=_maintenance(at_risk_aircraft=[]), EMISSIONS=_emissions(**o))


def test_emissions_route_check_is_listed_last_and_passes_on_a_match():
    decision = _run(_with_emissions())
    assert decision["constraints_checked"][-1] == "emissions_route_matches"
    assert _vr(decision)["conflicts"] == []


def test_emissions_check_absent_when_the_agent_is_absent():
    assert "emissions_route_matches" not in _run()["constraints_checked"]


def test_emissions_route_mismatch_is_blocking():
    decision = _run(_with_emissions(route="BLR-HYD"))
    assert any("emissions agent analyzed route BLR-HYD" in c for c in _vr(decision)["conflicts"])
    assert _vr(decision)["verdict"] == "REJECT"


def test_emissions_opposes_warns_without_blocking():
    decision = _run(_with_emissions(emissions_stance="OPPOSES"))
    assert [w for w in _vr(decision)["warnings"] if "Emissions agent opposes" in w and "BOM-DEL" in w]
    assert _vr(decision)["conflicts"] == []
    assert _vr(decision)["risk"] == "MEDIUM"


@pytest.mark.parametrize("stance", ["SUPPORTS", "NEUTRAL"])
def test_other_emissions_stances_do_not_warn(stance):
    assert _vr(_run(_with_emissions(emissions_stance=stance)))["warnings"] == []


def test_emissions_adds_no_money():
    base, with_emissions = _run(_all()), _run(_with_emissions())
    for key in ("expected_profit_impact", "expected_revenue_impact", "expected_cost_impact"):
        assert with_emissions[key] == base[key]


def test_low_emissions_confidence_warns():
    warnings = _vr(_run(_with_emissions(confidence=0.59)))["warnings"]
    assert [w for w in warnings if "EMISSIONS agent has low confidence" in w]

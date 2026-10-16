"""PRICING agent: schema, spec, search template and its place in the decision engine."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.pricing_agent import PRICING_AGENT_SPEC
from app.agents.registry import AGENT_REGISTRY
from app.agents.schemas import CITED_SOURCES_DESCRIPTION, PricingRecommendation
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.evidence.base import EvidenceRequest
from app.seed.seed import run_seed
from app.websearch.evidence import TEMPLATES, build_query
from tests.test_decision_reconcile_all import _all, _maintenance, _run, _vr


def _pricing(**o):
    base = dict(
        route="BOM-DEL", elasticity_used=-1.463, fare_change_to_fill_added_seats_pct=-38.9,
        revenue_change_if_fare_minus_5pct_usd=-120.5, revenue_change_if_fare_plus_5pct_usd=95.0,
        pricing_stance="OPPOSES", confidence=0.8, risks=["elasticity is a literature average"],
        reasoning="Filling the added seats needs a deep fare cut.", cited_sources=[],
    )
    base.update(o)
    return PricingRecommendation(**base)


# --- schema -----------------------------------------------------------------------------------

def test_schema_has_exactly_the_contract_fields():
    assert list(PricingRecommendation.model_fields) == [
        "route", "elasticity_used", "fare_change_to_fill_added_seats_pct", "revenue_change_if_fare_minus_5pct_usd",
        "revenue_change_if_fare_plus_5pct_usd", "pricing_stance", "confidence", "risks", "reasoning", "cited_sources",
    ]


def test_fare_change_may_be_null():
    assert _pricing(fare_change_to_fill_added_seats_pct=None).fare_change_to_fill_added_seats_pct is None


@pytest.mark.parametrize("field, value", [("pricing_stance", "LOVES"), ("confidence", -0.1), ("confidence", 1.1)])
def test_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        _pricing(**{field: value})


@pytest.mark.parametrize("missing", list(PricingRecommendation.model_fields))
def test_requires_every_field(missing):
    fields = _pricing().model_dump()
    del fields[missing]
    with pytest.raises(ValidationError):
        PricingRecommendation(**fields)


def test_field_descriptions_tell_the_model_to_copy_the_precomputed_values():
    fields = PricingRecommendation.model_fields
    assert "elasticity_used" in fields["elasticity_used"].description
    for name in ("fare_change_to_fill_added_seats_pct", "revenue_change_if_fare_minus_5pct_usd",
                 "revenue_change_if_fare_plus_5pct_usd", "pricing_stance"):
        assert "NETWORK" in fields[name].description and "MAINTAIN" in fields[name].description
    assert fields["cited_sources"].description == CITED_SOURCES_DESCRIPTION


# --- spec -------------------------------------------------------------------------------------

def test_spec_shape():
    assert PRICING_AGENT_SPEC.agent_type == "PRICING"
    assert PRICING_AGENT_SPEC.tool_name == "query_pricing_options"
    assert PRICING_AGENT_SPEC.output_schema is PricingRecommendation
    assert PRICING_AGENT_SPEC.entities_key == "pricing"
    assert PRICING_AGENT_SPEC.depends_on == ("NETWORK",)
    assert PRICING_AGENT_SPEC.evidence_providers == ("market_competition", "fuel_price", "web_search")
    assert PRICING_AGENT_SPEC.task_description == AGENT_TASKS["PRICING"]
    assert PRICING_AGENT_SPEC.tool_name == AGENT_TOOLS["PRICING"][0]
    assert AGENT_REGISTRY["PRICING"] is PRICING_AGENT_SPEC


def test_instructions_cover_the_network_route_the_precomputed_figures_and_the_guidance():
    text = PRICING_AGENT_SPEC.system_instructions
    for phrase in ("NETWORK", "impact_if_increase_by_one_weekly_flight", "impact_if_decrease_by_one_weekly_flight",
                   "pricing_stance", "MAINTAIN", "elasticity_sources", "Never estimate"):
        assert phrase in text
    assert text.endswith(EVIDENCE_GUIDANCE)


async def test_spec_tool_fn_runs_against_seeded_db(db_session):
    await run_seed(db_session)
    result = await PRICING_AGENT_SPEC.tool_fn(db_session)
    assert any(e["route"] == "BOM-DEL" for e in result["pricing"])


# --- web search template ----------------------------------------------------------------------

def test_pricing_search_template():
    assert TEMPLATES["PRICING"] == "{route} airfare trends India {year}"
    request = EvidenceRequest(agent_type="PRICING", objective="o", route="BOM-DEL", previous_results=[])
    now = datetime(2027, 3, 1, tzinfo=timezone.utc)
    assert build_query(request, now=now) == "BOM DEL airfare trends India 2027"


# --- decision engine --------------------------------------------------------------------------

def _with_pricing(**o):
    return _all(MAINTENANCE=_maintenance(at_risk_aircraft=[]), PRICING=_pricing(**o))


def test_pricing_route_check_is_listed_and_passes_on_a_match():
    decision = _run(_with_pricing(pricing_stance="NEUTRAL"))
    assert "pricing_route_matches" in decision["constraints_checked"]
    assert _vr(decision)["conflicts"] == []


def test_pricing_check_absent_when_the_agent_is_absent():
    assert "pricing_route_matches" not in _run()["constraints_checked"]


def test_pricing_route_mismatch_is_blocking():
    decision = _run(_with_pricing(route="BLR-HYD"))
    assert any("pricing agent analyzed route BLR-HYD" in c for c in _vr(decision)["conflicts"])
    assert _vr(decision)["verdict"] == "REJECT"


def test_pricing_opposes_warns_without_blocking():
    decision = _run(_with_pricing(pricing_stance="OPPOSES"))
    assert [w for w in _vr(decision)["warnings"] if "Pricing agent opposes" in w and "BOM-DEL" in w and "38.9" in w]
    assert _vr(decision)["conflicts"] == []
    assert _vr(decision)["risk"] == "MEDIUM"


@pytest.mark.parametrize("stance", ["SUPPORTS", "NEUTRAL"])
def test_other_pricing_stances_do_not_warn(stance):
    assert _vr(_run(_with_pricing(pricing_stance=stance)))["warnings"] == []


def test_pricing_opposes_without_a_fare_change_still_warns():
    decision = _run(_with_pricing(pricing_stance="OPPOSES", fare_change_to_fill_added_seats_pct=None))
    assert [w for w in _vr(decision)["warnings"] if "Pricing agent opposes" in w]


def test_pricing_adds_no_money():
    base, with_pricing = _run(_all()), _run(_with_pricing())
    for key in ("expected_profit_impact", "expected_revenue_impact", "expected_cost_impact"):
        assert with_pricing[key] == base[key]


def test_low_pricing_confidence_warns():
    decision = _run(_with_pricing(pricing_stance="NEUTRAL", confidence=0.1))
    assert any("PRICING agent has low confidence" in w for w in _vr(decision)["warnings"])

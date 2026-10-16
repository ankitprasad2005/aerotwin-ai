import pytest
from pydantic import ValidationError

from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.market_agent import MARKET_AGENT_SPEC
from app.agents.registry import AGENT_REGISTRY
from app.agents.schemas import CITED_SOURCES_DESCRIPTION, MarketRecommendation
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.decision.weights import DEFAULT_WEIGHTS
from app.evidence.base import EvidenceRequest
from app.websearch.evidence import build_query
from tests.test_decision_reconcile_all import _all, _network, _run, _vr


def _market(**o):
    base = dict(
        route="BOM-DEL", competition_level="MODERATE", rival_airlines=3, demand_outlook="STABLE",
        national_passenger_growth_pct=3.2, holidays_next_8_weeks=1, confidence=0.8, risks=["fare competition"],
        reasoning="r", cited_sources=[],
    )
    base.update(o)
    return MarketRecommendation(**base)


def test_spec_shape():
    spec = MARKET_AGENT_SPEC
    assert "MARKET" in AGENT_REGISTRY and AGENT_REGISTRY["MARKET"] is spec
    assert spec.agent_type == "MARKET" and spec.depends_on == ("NETWORK",)
    assert spec.tool_name == "query_market_conditions" == AGENT_TOOLS["MARKET"][0]
    assert spec.task_description == AGENT_TASKS["MARKET"]
    assert spec.output_schema is MarketRecommendation and spec.entities_key == "market"
    assert spec.evidence_providers == ("market_competition", "world_bank_demand", "india_holidays", "web_search")


def test_instructions_pin_the_route_and_the_precomputed_values():
    text = MARKET_AGENT_SPEC.system_instructions
    assert "`route` of the NETWORK entry" in text and "never substitute a different one" in text
    for name in ("rival_airlines", "competition_level", "demand_outlook", "holidays_next_8_weeks"):
        assert name in text
    assert "never recompute or invent" in text
    assert text.endswith(EVIDENCE_GUIDANCE)


def test_schema_has_exactly_the_contract_fields():
    assert list(MarketRecommendation.model_fields) == [
        "route", "competition_level", "rival_airlines", "demand_outlook", "national_passenger_growth_pct",
        "holidays_next_8_weeks", "confidence", "risks", "reasoning", "cited_sources",
    ]
    fields = MarketRecommendation.model_fields
    assert fields["cited_sources"].description == CITED_SOURCES_DESCRIPTION
    for name in ("competition_level", "rival_airlines", "demand_outlook", "national_passenger_growth_pct", "holidays_next_8_weeks"):
        assert "Copy" in fields[name].description
    assert _market(national_passenger_growth_pct=None).national_passenger_growth_pct is None


@pytest.mark.parametrize("field,value", [
    ("competition_level", "EXTREME"), ("demand_outlook", "HIGH"), ("confidence", 1.1), ("confidence", -0.1),
    ("rival_airlines", "many"),
])
def test_schema_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        _market(**{field: value})


def test_web_search_query_for_market():
    request = EvidenceRequest(agent_type="MARKET", objective="x", route="BOM-DEL", previous_results=[])
    assert build_query(request).startswith("BOM DEL airline competition fares India") or "airline competition fares india" in build_query(request).lower()


# --- decision engine ---------------------------------------------------------------------------


def test_market_route_check_is_listed_last_and_passes():
    decision = _run(_all(MARKET=_market()))

    assert decision["constraints_checked"][-1] == "market_route_matches"
    assert _vr(decision)["conflicts"] == []
    assert "fare competition" in decision["risks"]


def test_market_check_is_absent_without_the_market_agent():
    assert "market_route_matches" not in _run()["constraints_checked"]


def test_market_route_mismatch_is_a_blocking_conflict():
    vr = _vr(_run(_all(MARKET=_market(route="BLR-HYD"))))

    assert vr["constraints"] == "FAIL" and vr["verdict"] == "REJECT"
    assert vr["conflicts"] == ["Network agent analyzed route BOM-DEL but market agent analyzed route BLR-HYD."]


def _market_warnings(decision):
    return [w for w in _vr(decision)["warnings"] if w.startswith("Market agent")]


def test_weak_demand_with_an_increase_warns_without_blocking():
    vr = _vr(_run(_all(MARKET=_market(demand_outlook="WEAK"))))

    assert vr["conflicts"] == [] and vr["constraints"] == "PASS"
    assert [w for w in vr["warnings"] if w.startswith("Market agent")] == [
        "Market agent warns about BOM-DEL: the demand outlook is WEAK, but the network agent recommends increasing frequency."
    ]


def test_high_competition_with_an_increase_warns():
    decision = _run(_all(MARKET=_market(competition_level="HIGH", rival_airlines=6)))

    assert _market_warnings(decision) == [
        "Market agent warns about BOM-DEL: competition is HIGH (6 rival airlines), but the network agent recommends increasing frequency."
    ]


def test_weak_demand_and_high_competition_give_one_combined_warning():
    decision = _run(_all(MARKET=_market(demand_outlook="WEAK", competition_level="HIGH", rival_airlines=7)))

    assert len(_market_warnings(decision)) == 1
    assert "the demand outlook is WEAK and competition is HIGH (7 rival airlines)" in _market_warnings(decision)[0]


@pytest.mark.parametrize("outlook,level", [("STABLE", "MODERATE"), ("STRONG", "LOW"), ("STRONG", "MODERATE")])
def test_benign_market_does_not_warn(outlook, level):
    assert _market_warnings(_run(_all(MARKET=_market(demand_outlook=outlook, competition_level=level)))) == []


@pytest.mark.parametrize("action", ["DECREASE_FREQUENCY", "MAINTAIN"])
def test_market_warning_only_applies_to_increases(action):
    network = _network(action=action, expected_revenue_impact=0.0, expected_cost_impact=0.0, expected_profit_impact=0.0)
    recs = _all(NETWORK=network, MARKET=_market(demand_outlook="WEAK", competition_level="HIGH"))

    assert _market_warnings(_run(recs)) == []


def test_market_confidence_uses_its_default_weight():
    assert DEFAULT_WEIGHTS.agent_confidence["MARKET"] == 0.10
    low = _run(_all(MARKET=_market(confidence=0.1)))

    assert any(w == "MARKET agent has low confidence (0.10)." for w in _vr(low)["warnings"])

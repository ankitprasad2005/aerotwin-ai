import math

import pytest

from app.agents.schemas import (
    CargoRecommendation, CrewRecommendation, FinanceRecommendation, FleetRecommendation, MaintenanceRecommendation, NetworkRecommendation,
)
from app.decision.engine import (
    compute_score, evidence_reliability, reconcile_all, risk_level, sigmoid, verdict_for, weighted_confidence,
)
from app.decision.weights import DEFAULT_WEIGHTS, DecisionWeights


def _network(**o):
    base = dict(
        route="BOM-DEL", action="INCREASE_FREQUENCY", expected_profit_impact=125000.0,
        expected_revenue_impact=300000.0, expected_cost_impact=175000.0, confidence=0.82,
        risks=["fuel price volatility"], reasoning="r", cited_sources=[],
    )
    base.update(o)
    return NetworkRecommendation(**base)


def _fleet(**o):
    base = dict(
        route="BOM-DEL", aircraft_tail_number="VT-AER1", assignment_action="ASSIGN_ADDITIONAL_AIRCRAFT",
        aircraft_availability="AVAILABLE", expected_cost_impact=40000.0, confidence=0.88,
        risks=["crew scheduling"], reasoning="r", cited_sources=[],
    )
    base.update(o)
    return FleetRecommendation(**base)


def _maintenance(**o):
    base = dict(
        grounded_aircraft=["VT-AER3"], at_risk_aircraft=["VT-AER1"], actions=[], confidence=0.9,
        risks=["parts delay"], reasoning="r", cited_sources=[],
    )
    base.update(o)
    return MaintenanceRecommendation(**base)


def _crew(**o):
    base = dict(
        route="BOM-DEL", crew_availability="SUFFICIENT", assignment_action="ASSIGN_ADDITIONAL_CREW",
        assigned_crew=["CR-001"], expected_cost_impact=0.0, confidence=0.85, risks=["duty limits"],
        reasoning="r", cited_sources=[],
    )
    base.update(o)
    return CrewRecommendation(**base)


def _cargo(**o):
    base = dict(
        route="BOM-DEL", cargo_stance="SUPPORTS", expected_revenue_impact=2040.0, expected_cost_impact=510.0,
        confidence=0.8, risks=["freight demand volatility"], reasoning="r", cited_sources=[],
    )
    base.update(o)
    return CargoRecommendation(**base)


def _all(**overrides):
    recs = {
        "NETWORK": _network(), "FLEET": _fleet(), "MAINTENANCE": _maintenance(), "CREW": _crew(), "CARGO": _cargo(),
    }
    recs.update(overrides)
    return recs


def _run(recs=None, weights=DEFAULT_WEIGHTS, reliability=None):
    return reconcile_all(recs if recs is not None else _all(), weights=weights, evidence_reliability=reliability)


def _vr(decision):
    return decision["validation_result"]


def _weights(**changes):
    raw = DEFAULT_WEIGHTS.model_dump()
    raw.update(changes)
    return DecisionWeights.model_validate(raw)


def _only_factor(name, **changes):
    factors = {key: 0.0 for key in DEFAULT_WEIGHTS.factors}
    factors[name] = 1.0
    return _weights(factors=factors, **changes)


# --- the worked happy path ---------------------------------------------------------------------

def test_happy_path_worked_example():
    decision = _run()
    vr = _vr(decision)

    assert decision["summary"] == "Increase BOM-DEL frequency"
    assert decision["expected_revenue_impact"] == 302040.0
    assert decision["expected_cost_impact"] == 175000.0 + 40000.0 + 0.0 + 510.0
    assert decision["expected_profit_impact"] == pytest.approx(86530.0)
    assert vr["conflicts"] == []
    assert vr["constraints"] == "PASS"
    assert len(vr["warnings"]) == 1 and "VT-AER1" in vr["warnings"][0]  # at-risk aircraft
    assert vr["risk"] == "MEDIUM"
    assert vr["score"] == pytest.approx(86.98, abs=0.01)
    assert vr["verdict"] == "RECOMMEND"
    assert vr["schema"] == "PASS"
    assert decision["status"] == "RECOMMENDED"
    assert decision["confidence"] == 0.8
    assert decision["risks"] == ["fuel price volatility", "crew scheduling", "parts delay", "duty limits",
                                 "freight demand volatility"]


def test_score_breakdown_sums_to_score_and_shares_to_one():
    breakdown = _vr(_run())["score_breakdown"]

    assert set(breakdown) == set(DEFAULT_WEIGHTS.factors)
    assert sum(f["weight"] for f in breakdown.values()) == pytest.approx(1.0)
    assert sum(f["contribution"] for f in breakdown.values()) == pytest.approx(_vr(_run())["score"], abs=0.01)
    assert breakdown["feasibility"] == {"weight": 0.0, "value": 1.0, "contribution": 0.0}  # reported, not scored
    assert all(0 <= f["value"] <= 1 for f in breakdown.values())


def test_constraints_checked_lists_every_check_for_all_agents():
    assert _run()["constraints_checked"] == [
        "aircraft_availability_matches_action",
        "network_and_fleet_route_match",
        "fleet_assignment_matches_network_action",
        "change_has_positive_expected_profit",
        "aircraft_not_grounded",
        "crew_sufficient_for_increase",
        "crew_route_matches",
        "cargo_route_matches",
    ]


# --- required / optional agents ----------------------------------------------------------------

@pytest.mark.parametrize("missing", ["NETWORK", "FLEET"])
def test_network_and_fleet_are_required(missing):
    recs = _all()
    del recs[missing]
    with pytest.raises(ValueError, match=missing):
        _run(recs)


@pytest.mark.parametrize("dropped", [(), ("MAINTENANCE",), ("CREW",), ("CARGO",), ("MAINTENANCE", "CREW", "CARGO")])
def test_optional_agents_may_be_missing(dropped):
    recs = {k: v for k, v in _all().items() if k not in dropped}
    decision = _run(recs)

    assert _vr(decision)["verdict"] in ("RECOMMEND", "REVIEW", "REJECT")
    assert _vr(decision)["conflicts"] == []
    if "MAINTENANCE" in dropped:
        assert "aircraft_not_grounded" not in decision["constraints_checked"]
    if "CREW" in dropped:
        assert "crew_route_matches" not in decision["constraints_checked"]
    if "CARGO" in dropped:
        assert "cargo_route_matches" not in decision["constraints_checked"]


def test_only_required_agents_has_four_checks_and_no_warnings():
    decision = _run({"NETWORK": _network(), "FLEET": _fleet()})

    assert len(decision["constraints_checked"]) == 4
    assert _vr(decision)["warnings"] == []
    assert _vr(decision)["risk"] == "LOW"
    assert decision["expected_profit_impact"] == 300000.0 - 215000.0


# --- money -------------------------------------------------------------------------------------

def test_crew_cost_is_added_to_costs():
    base = _run()["expected_cost_impact"]
    assert _run(_all(CREW=_crew(expected_cost_impact=1200.0)))["expected_cost_impact"] == base + 1200.0


def test_cargo_money_counts_only_when_route_matches():
    mismatched = _run(_all(CARGO=_cargo(route="BLR-HYD")))

    assert mismatched["expected_revenue_impact"] == 300000.0
    assert mismatched["expected_cost_impact"] == 215000.0
    assert mismatched["expected_profit_impact"] == 85000.0


# --- blocking conflicts ------------------------------------------------------------------------

def test_fleet_assigns_grounded_aircraft_on_increase_is_blocking():
    decision = _run(_all(MAINTENANCE=_maintenance(grounded_aircraft=["VT-AER1"])))

    assert any("GROUNDED" in c for c in _vr(decision)["conflicts"])
    assert _vr(decision)["verdict"] == "REJECT"
    assert _vr(decision)["risk"] == "HIGH"
    assert _vr(decision)["constraints"] == "FAIL"


def test_grounded_aircraft_is_not_a_conflict_when_not_increasing():
    recs = _all(
        NETWORK=_network(action="DECREASE_FREQUENCY", expected_revenue_impact=-1000.0, expected_cost_impact=-5000.0),
        FLEET=_fleet(assignment_action="NO_CHANGE", expected_cost_impact=0.0),
        MAINTENANCE=_maintenance(grounded_aircraft=["VT-AER1"]),
        CARGO=_cargo(cargo_stance="NEUTRAL", expected_revenue_impact=0.0, expected_cost_impact=0.0),
    )
    assert _vr(_run(recs))["conflicts"] == []


def test_crew_insufficient_on_increase_is_blocking():
    decision = _run(_all(CREW=_crew(crew_availability="INSUFFICIENT", assignment_action="NO_CHANGE", assigned_crew=[])))

    assert any("INSUFFICIENT" in c for c in _vr(decision)["conflicts"])
    assert _vr(decision)["verdict"] == "REJECT"


def test_crew_insufficient_is_fine_when_not_increasing():
    recs = _all(
        NETWORK=_network(action="MAINTAIN", expected_revenue_impact=0.0, expected_cost_impact=0.0),
        FLEET=_fleet(assignment_action="NO_CHANGE", expected_cost_impact=0.0),
        CREW=_crew(crew_availability="INSUFFICIENT", assignment_action="NO_CHANGE", assigned_crew=[]),
        CARGO=_cargo(cargo_stance="NEUTRAL", expected_revenue_impact=0.0, expected_cost_impact=0.0),
    )
    assert _vr(_run(recs))["conflicts"] == []


def test_crew_route_mismatch_is_blocking():
    decision = _run(_all(CREW=_crew(route="BLR-HYD")))

    assert any("crew agent analyzed route BLR-HYD" in c for c in _vr(decision)["conflicts"])
    assert _vr(decision)["verdict"] == "REJECT"


def test_cargo_route_mismatch_is_blocking():
    decision = _run(_all(CARGO=_cargo(route="BLR-HYD")))

    assert any("cargo agent analyzed route BLR-HYD" in c for c in _vr(decision)["conflicts"])
    assert _vr(decision)["verdict"] == "REJECT"


@pytest.mark.parametrize(
    "recs,needle",
    [
        ({"FLEET": _fleet(aircraft_availability="UNAVAILABLE")}, "UNAVAILABLE"),
        ({"FLEET": _fleet(route="BLR-HYD")}, "fleet agent analyzed route"),
        ({"FLEET": _fleet(assignment_action="NO_CHANGE", expected_cost_impact=0.0)}, "NO_CHANGE"),
        ({"NETWORK": _network(action="MAINTAIN", expected_revenue_impact=0.0, expected_cost_impact=0.0)},
         "ASSIGN_ADDITIONAL_AIRCRAFT"),
        ({"NETWORK": _network(expected_revenue_impact=1000.0, expected_cost_impact=900000.0)}, "doesn't pay"),
    ],
)
def test_existing_conflicts_still_block(recs, needle):
    decision = _run(_all(**recs))

    assert any(needle in c for c in _vr(decision)["conflicts"])
    assert _vr(decision)["verdict"] == "REJECT"
    assert _vr(decision)["risk"] == "HIGH"


def test_feasibility_is_share_of_checks_passed():
    decision = _run(_all(CREW=_crew(route="BLR-HYD")))

    # one failed check out of eight
    assert _vr(decision)["score_breakdown"]["feasibility"]["value"] == pytest.approx(7 / 8)


# --- warnings ----------------------------------------------------------------------------------

def test_at_risk_aircraft_warns_without_blocking():
    decision = _run(_all())
    assert any("at risk" in w for w in _vr(decision)["warnings"])
    assert _vr(decision)["conflicts"] == []


def test_no_warning_when_aircraft_is_not_at_risk():
    decision = _run(_all(MAINTENANCE=_maintenance(at_risk_aircraft=[])))
    assert _vr(decision)["warnings"] == []
    assert _vr(decision)["risk"] == "LOW"


def test_cargo_opposes_warns_without_blocking():
    decision = _run(_all(
        MAINTENANCE=_maintenance(at_risk_aircraft=[]), CARGO=_cargo(cargo_stance="OPPOSES"),
    ))
    assert [w for w in _vr(decision)["warnings"] if "Cargo" in w]
    assert _vr(decision)["conflicts"] == []
    assert _vr(decision)["risk"] == "MEDIUM"


def test_crew_reposition_with_cost_warns():
    decision = _run(_all(
        MAINTENANCE=_maintenance(at_risk_aircraft=[]),
        CREW=_crew(assignment_action="REPOSITION_CREW", expected_cost_impact=900.0),
    ))
    assert [w for w in _vr(decision)["warnings"] if "repositioned" in w]


def test_crew_reposition_without_cost_does_not_warn():
    decision = _run(_all(
        MAINTENANCE=_maintenance(at_risk_aircraft=[]),
        CREW=_crew(assignment_action="REPOSITION_CREW", expected_cost_impact=0.0),
    ))
    assert _vr(decision)["warnings"] == []


@pytest.mark.parametrize("agent", ["NETWORK", "FLEET", "MAINTENANCE", "CREW", "CARGO"])
def test_low_confidence_of_any_agent_warns(agent):
    makers = {"NETWORK": _network, "FLEET": _fleet, "MAINTENANCE": _maintenance, "CREW": _crew, "CARGO": _cargo}
    recs = _all(MAINTENANCE=_maintenance(at_risk_aircraft=[]))
    recs[agent] = makers[agent](confidence=0.59) if agent != "MAINTENANCE" else _maintenance(
        at_risk_aircraft=[], confidence=0.59)
    warnings = _vr(_run(recs))["warnings"]

    assert [w for w in warnings if f"{agent} agent has low confidence" in w]


def test_confidence_exactly_point_six_does_not_warn():
    decision = _run(_all(MAINTENANCE=_maintenance(at_risk_aircraft=[]), NETWORK=_network(confidence=0.6)))
    assert _vr(decision)["warnings"] == []


def test_each_warning_costs_fifteen_points_of_risk():
    decision = _run(_all())  # exactly one warning (at-risk aircraft)
    assert _vr(decision)["score_breakdown"]["risk"]["value"] == pytest.approx(0.85)


def test_risk_factor_floors_at_zero():
    recs = _all(
        FLEET=_fleet(aircraft_availability="UNAVAILABLE", route="X-Y", assignment_action="NO_CHANGE"),
        CREW=_crew(route="Q-R", crew_availability="INSUFFICIENT"),
    )
    assert _vr(_run(recs))["score_breakdown"]["risk"]["value"] == 0.0


# --- risk level --------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "blocking,warnings,confidence,expected",
    [(1, 0, 0.99, "HIGH"), (2, 3, 0.1, "HIGH"), (0, 1, 0.99, "MEDIUM"), (0, 0, 0.69, "MEDIUM"),
     (0, 0, 0.7, "LOW"), (0, 0, 1.0, "LOW")],
)
def test_risk_level(blocking, warnings, confidence, expected):
    assert risk_level(blocking, warnings, confidence) == expected


# --- sigmoid / profit factor -------------------------------------------------------------------

def test_profit_zero_gives_one_half():
    assert sigmoid(0) == 0.5
    recs = _all(
        NETWORK=_network(action="MAINTAIN", expected_revenue_impact=0.0, expected_cost_impact=0.0),
        FLEET=_fleet(assignment_action="NO_CHANGE", expected_cost_impact=0.0),
        CARGO=_cargo(cargo_stance="NEUTRAL", expected_revenue_impact=0.0, expected_cost_impact=0.0),
    )
    decision = _run(recs)
    assert decision["expected_profit_impact"] == 0
    assert _vr(decision)["score_breakdown"]["profit"]["value"] == 0.5


@pytest.mark.parametrize("x", [1e9, -1e9, 1e308, -1e308, 710.0, -710.0, math.inf, -math.inf])
def test_sigmoid_never_overflows(x):
    value = sigmoid(x)
    assert 0.0 <= value <= 1.0


def test_sigmoid_saturates_and_is_monotonic():
    assert sigmoid(1e9) == 1.0
    assert sigmoid(-1e9) == 0.0
    assert sigmoid(-1) < sigmoid(0) < sigmoid(1)
    assert sigmoid(1) + sigmoid(-1) == pytest.approx(1.0)
    assert sigmoid(math.nan) == 0.5


@pytest.mark.parametrize("sign", [1, -1])
def test_huge_profit_does_not_overflow(sign):
    recs = _all(NETWORK=_network(expected_revenue_impact=sign * 1e300, expected_cost_impact=0.0))
    decision = _run(recs, weights=_weights(profit_scale_usd=1e-300))

    assert _vr(decision)["score_breakdown"]["profit"]["value"] in (0.0, 1.0)


def test_profit_scale_changes_the_steepness():
    gentle = _vr(_run(weights=_weights(profit_scale_usd=1e6)))["score_breakdown"]["profit"]["value"]
    steep = _vr(_run(weights=_weights(profit_scale_usd=1e3)))["score_breakdown"]["profit"]["value"]
    assert 0.5 < gentle < steep


# --- confidence factor -------------------------------------------------------------------------

def test_confidence_is_agent_weighted_mean():
    value = _vr(_run())["score_breakdown"]["confidence"]["value"]
    assert value == pytest.approx(0.35 * 0.82 + 0.2 * 0.88 + 0.15 * 0.9 + 0.15 * 0.85 + 0.15 * 0.8)


def test_confidence_mean_is_over_present_agents_only():
    value = _vr(_run({"NETWORK": _network(), "FLEET": _fleet()}))["score_breakdown"]["confidence"]["value"]
    assert value == pytest.approx((0.35 * 0.82 + 0.2 * 0.88) / 0.55)


def test_confidence_falls_back_to_plain_mean_when_present_weights_are_zero():
    weights = _weights(agent_confidence={"NETWORK": 0, "FLEET": 0, "MAINTENANCE": 1, "CREW": 0, "CARGO": 0})
    recs = {"NETWORK": _network(confidence=0.6), "FLEET": _fleet(confidence=0.8)}

    assert weighted_confidence(recs, weights) == pytest.approx(0.7)


# --- data quality ------------------------------------------------------------------------------

def test_data_quality_defaults_to_half_when_nothing_cited():
    assert _vr(_run(reliability=None))["score_breakdown"]["data_quality"]["value"] == 0.5


def test_data_quality_uses_given_reliability():
    assert _vr(_run(reliability=0.9))["score_breakdown"]["data_quality"]["value"] == 0.9


def test_evidence_reliability_means_only_cited_items():
    recs = {"NETWORK": _network(cited_sources=["a", "b", "missing"]), "FLEET": _fleet(cited_sources=["b", "c"])}
    evidence = {
        "NETWORK": [{"id": "a", "reliability": 0.9}, {"id": "b", "reliability": 0.7}, {"id": "z", "reliability": 0.0}],
        "FLEET": [{"id": "b", "reliability": 0.7}, {"id": "c", "reliability": 0.4}],
    }
    assert evidence_reliability(recs, evidence) == pytest.approx((0.9 + 0.7 + 0.4) / 3)


def test_evidence_reliability_none_when_nothing_cited_or_nothing_matches():
    assert evidence_reliability({"NETWORK": _network(), "FLEET": _fleet()}, {"NETWORK": [{"id": "a", "reliability": 1}]}) is None
    assert evidence_reliability({"NETWORK": _network(cited_sources=["x"])}, {"NETWORK": []}) is None


def test_evidence_reliability_ignores_malformed_items_and_clamps():
    recs = {"NETWORK": _network(cited_sources=["a", "b", "c", "d", "e"])}
    evidence = {"NETWORK": [
        {"id": "a", "reliability": "high"}, {"id": "b", "reliability": True}, {"id": "c", "reliability": math.nan},
        {"id": "d", "reliability": 5}, {"id": "e", "reliability": -2}, {"reliability": 0.5},
    ]}
    assert evidence_reliability(recs, evidence) == pytest.approx(0.5)  # d clamps to 1, e clamps to 0


def test_evidence_reliability_only_counts_citations_of_evidence_the_citing_agent_received():
    # The fleet agent cites the network agent's item "m", which it never saw: that citation is invented.
    recs = {"NETWORK": _network(cited_sources=["m"]), "FLEET": _fleet(cited_sources=["m", "f"])}
    evidence = {"NETWORK": [{"id": "m", "reliability": 0.7}], "FLEET": [{"id": "f", "reliability": 0.9}]}
    assert evidence_reliability(recs, evidence) == pytest.approx((0.7 + 0.9) / 2)
    recs = {"NETWORK": _network(), "FLEET": _fleet(cited_sources=["m"])}
    assert evidence_reliability(recs, evidence) is None


# --- verdict thresholds ------------------------------------------------------------------------

@pytest.mark.parametrize(
    "score,blocking,expected",
    [
        (100, 0, "RECOMMEND"), (76, 0, "RECOMMEND"), (75.99, 0, "REVIEW"), (66, 0, "REVIEW"),
        (65.99, 0, "REJECT"), (0, 0, "REJECT"), (100, 1, "REJECT"), (76, 3, "REJECT"),
    ],
)
def test_verdict_thresholds(score, blocking, expected):
    assert verdict_for(score, blocking, DEFAULT_WEIGHTS) == expected


def test_custom_thresholds_are_honoured():
    weights = _weights(thresholds={"recommend": 90, "review": 80})
    assert verdict_for(89.99, 0, weights) == "REVIEW"
    assert verdict_for(90, 0, weights) == "RECOMMEND"
    assert verdict_for(79.99, 0, weights) == "REJECT"


def test_reconcile_verdict_at_exactly_the_recommend_threshold():
    # Only the feasibility factor counts, and it is 1.0 -> score exactly 100, thresholds at 100/0.
    weights = _only_factor("feasibility", thresholds={"recommend": 100, "review": 50})
    decision = _run({"NETWORK": _network(), "FLEET": _fleet()}, weights=weights)
    assert _vr(decision)["score"] == 100.0
    assert _vr(decision)["verdict"] == "RECOMMEND"


def test_reconcile_verdict_just_below_threshold_is_review():
    # 7 of 8 checks pass -> feasibility-only score 87.5
    recs = _all(CREW=_crew(route="BLR-HYD"))
    recs_no_block = _all(MAINTENANCE=_maintenance(at_risk_aircraft=[]))
    weights = _only_factor("feasibility", thresholds={"recommend": 87.5, "review": 50})
    assert _vr(_run(recs_no_block, weights))["verdict"] == "RECOMMEND"
    assert _vr(_run(recs, weights))["verdict"] == "REJECT"  # blocking conflict overrides the score


def test_score_is_rounded_to_two_decimals_and_verdict_uses_the_rounded_score():
    weights = _only_factor("confidence", thresholds={"recommend": 70, "review": 45})
    recs = {"NETWORK": _network(confidence=0.69996), "FLEET": _fleet(confidence=0.69996)}
    decision = _run(recs, weights=weights)

    assert _vr(decision)["score"] == 70.0
    assert _vr(decision)["verdict"] == "RECOMMEND"


def test_blocking_conflict_with_perfect_score_still_rejects():
    weights = _only_factor("confidence")
    recs = _all(CREW=_crew(route="BLR-HYD", confidence=1.0), NETWORK=_network(confidence=1.0),
                FLEET=_fleet(confidence=1.0), MAINTENANCE=_maintenance(confidence=1.0),
                CARGO=_cargo(confidence=1.0))
    decision = _run(recs, weights=weights)

    assert _vr(decision)["score"] == 100.0
    assert _vr(decision)["verdict"] == "REJECT"


def test_compute_score_normalises_weights():
    weights = _weights(factors={"profit": 2, "confidence": 2, "feasibility": 2, "risk": 2, "data_quality": 2})
    score, breakdown = compute_score({k: 1.0 for k in weights.factors}, weights)

    assert score == pytest.approx(100.0)
    assert breakdown["profit"]["weight"] == pytest.approx(0.2)


# --- finance ------------------------------------------------------------------------------------

def _finance(**o):
    base = dict(
        route="BOM-DEL", break_even_fuel_price_usd_per_gallon=3.77, fuel_headroom_pct=71.43,
        profit_change_if_fuel_up_10pct_usd=-280.0, profit_change_if_inr_weakens_5pct_usd=-476.19,
        financial_risk="LOW", confidence=0.75, risks=["jet fuel price spike"], reasoning="r", cited_sources=[],
    )
    base.update(o)
    return FinanceRecommendation(**base)


def test_finance_adds_a_route_check_and_changes_no_money():
    without, with_finance = _run(_all()), _run(_all(FINANCE=_finance()))

    assert "finance_route_matches" in with_finance["constraints_checked"]
    assert len(with_finance["constraints_checked"]) == len(without["constraints_checked"]) + 1
    assert _vr(with_finance)["conflicts"] == []
    for key in ("expected_revenue_impact", "expected_cost_impact", "expected_profit_impact"):
        assert with_finance[key] == without[key]  # sensitivity, not cash


def test_finance_absent_has_no_finance_check():
    assert "finance_route_matches" not in _run(_all())["constraints_checked"]


def test_finance_route_mismatch_is_blocking():
    decision = _run(_all(FINANCE=_finance(route="BLR-HYD")))

    assert any("finance agent analyzed route BLR-HYD" in c for c in _vr(decision)["conflicts"])
    assert _vr(decision)["verdict"] == "REJECT"
    assert _vr(decision)["risk"] == "HIGH"


def test_high_financial_risk_warns_without_blocking():
    decision = _run(_all(MAINTENANCE=_maintenance(at_risk_aircraft=[]), FINANCE=_finance(financial_risk="HIGH")))

    assert [w for w in _vr(decision)["warnings"] if "HIGH financial risk" in w]
    assert _vr(decision)["conflicts"] == []
    assert _vr(decision)["risk"] == "MEDIUM"


@pytest.mark.parametrize("risk", ["LOW", "MODERATE"])
def test_lower_financial_risk_does_not_warn(risk):
    decision = _run(_all(MAINTENANCE=_maintenance(at_risk_aircraft=[]), FINANCE=_finance(financial_risk=risk)))
    assert _vr(decision)["warnings"] == []


def test_high_financial_risk_does_not_warn_for_maintain():
    recs = _all(
        NETWORK=_network(action="MAINTAIN", expected_revenue_impact=0.0, expected_cost_impact=0.0),
        FLEET=_fleet(assignment_action="NO_CHANGE", expected_cost_impact=0.0),
        MAINTENANCE=_maintenance(at_risk_aircraft=[]),
        CARGO=_cargo(cargo_stance="NEUTRAL", expected_revenue_impact=0.0, expected_cost_impact=0.0),
        FINANCE=_finance(financial_risk="HIGH"),
    )
    assert _vr(_run(recs))["warnings"] == []


def test_high_financial_risk_warns_for_decrease():
    recs = _all(
        NETWORK=_network(action="DECREASE_FREQUENCY", expected_revenue_impact=-1000.0, expected_cost_impact=-5000.0),
        FLEET=_fleet(assignment_action="NO_CHANGE", expected_cost_impact=0.0),
        MAINTENANCE=_maintenance(at_risk_aircraft=[]),
        CARGO=_cargo(cargo_stance="NEUTRAL", expected_revenue_impact=0.0, expected_cost_impact=0.0),
        FINANCE=_finance(financial_risk="HIGH"),
    )
    assert [w for w in _vr(_run(recs))["warnings"] if "HIGH financial risk" in w]


def test_finance_confidence_is_weighted_and_low_confidence_warns():
    decision = _run(_all(MAINTENANCE=_maintenance(at_risk_aircraft=[]), FINANCE=_finance(confidence=0.1)))
    assert [w for w in _vr(decision)["warnings"] if "FINANCE agent has low confidence" in w]

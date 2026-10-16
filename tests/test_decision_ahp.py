import pytest

from app.decision.ahp import FACTOR_JUDGEMENTS, ahp_weights, consistency_ratio
from app.decision.engine import compute_score, sigmoid
from app.decision.weights import DEFAULT_WEIGHTS


def test_ahp_weights_of_a_consistent_matrix_are_exact():
    # a is twice b, b is twice c: perfectly consistent, weights 4:2:1.
    weights = ahp_weights(["a", "b", "c"], {("a", "b"): 2, ("a", "c"): 4, ("b", "c"): 2})
    assert weights == pytest.approx({"a": 4 / 7, "b": 2 / 7, "c": 1 / 7})


def test_consistency_ratio_is_zero_for_a_consistent_matrix_and_positive_otherwise():
    assert consistency_ratio(["a", "b", "c"], {("a", "b"): 2, ("a", "c"): 4, ("b", "c"): 2}) == pytest.approx(0, abs=1e-9)
    assert consistency_ratio(["a", "b", "c"], {("a", "b"): 3, ("a", "c"): 1, ("b", "c"): 3}) > 0.1


def test_every_pair_of_scored_factors_is_judged_once():
    factors = {"profit", "confidence", "risk", "data_quality"}
    pairs = {frozenset(pair) for pair in FACTOR_JUDGEMENTS}
    assert len(pairs) == len(FACTOR_JUDGEMENTS) == 6
    assert all(set(pair) <= factors for pair in FACTOR_JUDGEMENTS)


def test_the_factor_judgements_are_consistent_enough():
    assert consistency_ratio(["profit", "confidence", "risk", "data_quality"], FACTOR_JUDGEMENTS) < 0.1


def test_default_factor_weights_come_from_the_ahp_and_feasibility_is_not_scored():
    derived = ahp_weights(["profit", "confidence", "risk", "data_quality"], FACTOR_JUDGEMENTS)
    assert DEFAULT_WEIGHTS.factors["feasibility"] == 0
    for factor, weight in derived.items():
        assert DEFAULT_WEIGHTS.factors[factor] == pytest.approx(weight, abs=0.0005)


def _clean_decision_score(profit_usd: float) -> float:
    """A decision with every check passed, no warnings, agent confidence 0.7 and neutral data quality."""
    values = {
        "profit": sigmoid(profit_usd / DEFAULT_WEIGHTS.profit_scale_usd), "confidence": 0.7,
        "feasibility": 1.0, "risk": 1.0, "data_quality": 0.5,
    }
    return compute_score(values, DEFAULT_WEIGHTS)[0]


def test_thresholds_are_anchored_on_reference_decisions():
    # REVIEW starts at a break-even change; RECOMMEND at one that earns the profit scale per week.
    assert DEFAULT_WEIGHTS.thresholds["review"] == round(_clean_decision_score(0))
    assert DEFAULT_WEIGHTS.thresholds["recommend"] == round(_clean_decision_score(DEFAULT_WEIGHTS.profit_scale_usd))


def test_a_marginal_change_is_no_longer_recommended():
    assert _clean_decision_score(500) < DEFAULT_WEIGHTS.thresholds["recommend"]
    assert _clean_decision_score(15000) >= DEFAULT_WEIGHTS.thresholds["recommend"]

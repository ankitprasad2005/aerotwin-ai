from app.decision.engine import reconcile_all
from app.decision.weights import DEFAULT_WEIGHTS
from tests.test_decision_reconcile_all import _all, _network

CHECK = "network_evaluates_proposed_change"


def _run(recs, proposal):
    return reconcile_all(recs, weights=DEFAULT_WEIGHTS, evidence_reliability=None, proposed_change=proposal)


def test_no_proposal_adds_no_check():
    decision = reconcile_all(_all(), weights=DEFAULT_WEIGHTS, evidence_reliability=None)
    assert CHECK not in decision["constraints_checked"]


def test_answering_the_proposed_change_passes():
    network = _network()
    decision = _run(_all(), {"route": network.route, "action": network.action})
    assert CHECK in decision["constraints_checked"]
    assert decision["validation_result"]["conflicts"] == []


def test_answering_a_different_action_is_a_conflict_and_rejects():
    network = _network()
    decision = _run(_all(), {"route": network.route, "action": "DECREASE_FREQUENCY"})
    conflicts = decision["validation_result"]["conflicts"]
    assert len(conflicts) == 1 and "DECREASE_FREQUENCY" in conflicts[0] and network.action in conflicts[0]
    assert decision["validation_result"]["verdict"] == "REJECT"


def test_answering_a_different_route_is_a_conflict():
    decision = _run(_all(), {"route": "MAA-CCU", "action": _network().action})
    assert any("MAA-CCU" in c for c in decision["validation_result"]["conflicts"])

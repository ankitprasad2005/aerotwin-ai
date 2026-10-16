import pytest

from app.agents.schemas import WeatherRecommendation
from app.decision.weights import DEFAULT_WEIGHTS
from tests.test_decision_reconcile_all import _all, _network, _run, _vr


def _weather(**o):
    base = dict(
        route="BOM-DEL", origin_flight_category="VFR", destination_flight_category="VFR", weather_risk="LOW",
        disruption_days_next_7=0, confidence=0.85, risks=["monsoon squalls"], reasoning="r", cited_sources=[],
    )
    base.update(o)
    return WeatherRecommendation(**base)


def test_weather_route_check_is_listed_after_the_other_checks_and_passes():
    decision = _run(_all(WEATHER=_weather()))

    assert decision["constraints_checked"][-1] == "weather_route_matches"
    assert _vr(decision)["conflicts"] == []
    assert "monsoon squalls" in decision["risks"]


def test_weather_check_is_absent_without_the_weather_agent():
    assert "weather_route_matches" not in _run()["constraints_checked"]


def test_weather_route_mismatch_is_a_blocking_conflict():
    decision = _run(_all(WEATHER=_weather(route="BLR-HYD")))
    vr = _vr(decision)

    assert vr["constraints"] == "FAIL" and vr["verdict"] == "REJECT" and vr["risk"] == "HIGH"
    assert vr["conflicts"] == ["Network agent analyzed route BOM-DEL but weather agent analyzed route BLR-HYD."]


@pytest.mark.parametrize("risk", ["LOW", "MODERATE"])
def test_low_and_moderate_weather_risk_do_not_warn(risk):
    vr = _vr(_run(_all(WEATHER=_weather(weather_risk=risk, disruption_days_next_7=2))))

    assert not any("Weather risk" in w for w in vr["warnings"])


def test_high_weather_risk_with_an_increase_warns_without_blocking():
    base = _vr(_run(_all()))
    vr = _vr(_run(_all(WEATHER=_weather(weather_risk="HIGH", disruption_days_next_7=4))))

    assert vr["conflicts"] == [] and vr["constraints"] == "PASS"
    assert [w for w in vr["warnings"] if "Weather risk" in w] == [
        "Weather risk is HIGH on BOM-DEL (4 disrupted day(s) in the next 7), but the network agent recommends increasing frequency."
    ]
    assert len(vr["warnings"]) == len(base["warnings"]) + 1
    assert vr["risk"] == "MEDIUM"


@pytest.mark.parametrize("action", ["DECREASE_FREQUENCY", "MAINTAIN"])
def test_high_weather_risk_does_not_warn_when_not_increasing(action):
    network = _network(action=action, expected_revenue_impact=0.0, expected_cost_impact=0.0, expected_profit_impact=0.0)
    recs = _all(NETWORK=network, WEATHER=_weather(weather_risk="HIGH", disruption_days_next_7=4))

    assert not any("Weather risk" in w for w in _vr(_run(recs))["warnings"])


def test_weather_confidence_uses_its_default_weight():
    assert "WEATHER" in DEFAULT_WEIGHTS.agent_confidence
    low = _run(_all(WEATHER=_weather(confidence=0.1)))

    assert low["confidence"] == 0.1
    assert any(w == "WEATHER agent has low confidence (0.10)." for w in _vr(low)["warnings"])


def test_weather_adds_no_money():
    assert _run(_all(WEATHER=_weather()))["expected_profit_impact"] == _run()["expected_profit_impact"]

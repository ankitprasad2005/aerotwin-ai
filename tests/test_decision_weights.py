import copy

import pytest
from pydantic import ValidationError

from app.decision.weights import DEFAULT_WEIGHTS, DecisionWeights, load_weights, weights_to_dict
from app.models.external import DecisionWeightProfile


def _raw(**changes):
    raw = copy.deepcopy(DEFAULT_WEIGHTS.model_dump())
    raw.update(changes)
    return raw


def test_defaults_match_the_spec():
    assert DEFAULT_WEIGHTS.factors == {
        "profit": 0.30, "confidence": 0.20, "feasibility": 0.25, "risk": 0.15, "data_quality": 0.10,
    }
    assert DEFAULT_WEIGHTS.agent_confidence["NETWORK"] == 0.35
    assert DEFAULT_WEIGHTS.thresholds == {"recommend": 70, "review": 45}
    assert DEFAULT_WEIGHTS.profit_scale_usd == 10000


def test_round_trips_through_a_dict():
    assert DecisionWeights.model_validate(weights_to_dict(DEFAULT_WEIGHTS)) == DEFAULT_WEIGHTS


@pytest.mark.parametrize("group,key", [("factors", "profit"), ("agent_confidence", "CREW")])
def test_negative_weight_rejected(group, key):
    raw = _raw()
    raw[group][key] = -0.1
    with pytest.raises(ValidationError):
        DecisionWeights.model_validate(raw)


@pytest.mark.parametrize("group", ["factors", "agent_confidence"])
def test_zero_sum_group_rejected(group):
    raw = _raw()
    raw[group] = {key: 0 for key in raw[group]}
    with pytest.raises(ValidationError, match="greater than 0"):
        DecisionWeights.model_validate(raw)


@pytest.mark.parametrize("group", ["factors", "agent_confidence", "thresholds"])
def test_unknown_and_missing_keys_rejected(group):
    unknown = _raw()
    unknown[group]["bogus"] = 1
    with pytest.raises(ValidationError, match="exactly"):
        DecisionWeights.model_validate(unknown)
    missing = _raw()
    missing[group].pop(next(iter(missing[group])))
    with pytest.raises(ValidationError, match="exactly"):
        DecisionWeights.model_validate(missing)


@pytest.mark.parametrize(
    "thresholds",
    [
        {"recommend": 50, "review": 50},
        {"recommend": 40, "review": 60},
        {"recommend": 101, "review": 10},
        {"recommend": 70, "review": -1},
    ],
)
def test_bad_thresholds_rejected(thresholds):
    with pytest.raises(ValidationError):
        DecisionWeights.model_validate(_raw(thresholds=thresholds))


def test_threshold_edges_accepted():
    DecisionWeights.model_validate(_raw(thresholds={"recommend": 100, "review": 0}))


@pytest.mark.parametrize("scale", [0, -5])
def test_profit_scale_must_be_positive(scale):
    with pytest.raises(ValidationError):
        DecisionWeights.model_validate(_raw(profit_scale_usd=scale))


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_numbers_rejected(value):
    raw = _raw()
    raw["factors"]["profit"] = value
    with pytest.raises(ValidationError):
        DecisionWeights.model_validate(raw)
    with pytest.raises(ValidationError):
        DecisionWeights.model_validate(_raw(profit_scale_usd=value))


async def test_load_weights_defaults_without_profile(db_session):
    assert await load_weights(db_session) == DEFAULT_WEIGHTS


async def test_load_weights_reads_the_default_profile(db_session):
    db_session.add(DecisionWeightProfile(name="default", weights=_raw(profit_scale_usd=500)))
    await db_session.flush()
    assert (await load_weights(db_session)).profit_scale_usd == 500


async def test_load_weights_falls_back_when_stored_profile_is_invalid(db_session):
    db_session.add(DecisionWeightProfile(name="default", weights={"factors": {}}))
    await db_session.flush()
    assert await load_weights(db_session) == DEFAULT_WEIGHTS


LEGACY_AGENTS = {"NETWORK": 0.35, "FLEET": 0.20, "MAINTENANCE": 0.15, "CREW": 0.15, "CARGO": 0.15}


def test_defaults_cover_the_weather_finance_and_emissions_agents():
    assert DEFAULT_WEIGHTS.agent_confidence == {
        **LEGACY_AGENTS, "WEATHER": 0.10, "FINANCE": 0.10, "EMISSIONS": 0.05,
    }


def test_a_legacy_five_agent_profile_gets_the_new_agents_default_weights():
    weights = DecisionWeights.model_validate(_raw(agent_confidence={**LEGACY_AGENTS, "NETWORK": 0.5}))
    assert weights.agent_confidence["NETWORK"] == 0.5
    assert weights.agent_confidence["WEATHER"] == 0.10
    assert weights.agent_confidence["FINANCE"] == 0.10
    assert weights.agent_confidence["EMISSIONS"] == 0.05


def test_a_profile_missing_only_some_new_agents_is_still_rejected():
    with pytest.raises(ValidationError, match="exactly"):
        DecisionWeights.model_validate(_raw(agent_confidence={**LEGACY_AGENTS, "WEATHER": 0.1}))


async def test_load_weights_upgrades_a_stored_legacy_profile(db_session):
    db_session.add(DecisionWeightProfile(name="default", weights=_raw(agent_confidence=dict(LEGACY_AGENTS), profit_scale_usd=500)))
    await db_session.flush()
    weights = await load_weights(db_session)
    assert weights.profit_scale_usd == 500
    assert weights.agent_confidence["EMISSIONS"] == 0.05

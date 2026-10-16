import pytest

from app.agents.registry import AGENT_REGISTRY, RegistryError, validate_registry
from app.agents.schemas import NetworkRecommendation
from app.agents.spec import AgentSpec


async def _tool(db):
    return {"entities": []}


def _spec(name, *deps):
    return AgentSpec(
        agent_type=name, task_description="t", system_instructions="s", tool_name="tool",
        tool_fn=_tool, output_schema=NetworkRecommendation, depends_on=tuple(deps),
    )


def test_default_registry_lists_every_agent_after_its_dependencies():
    assert list(AGENT_REGISTRY) == ["NETWORK", "MAINTENANCE", "FLEET", "CREW", "CARGO", "FINANCE"]
    seen = set()
    for agent_type, spec in AGENT_REGISTRY.items():
        assert set(spec.depends_on) <= seen
        seen.add(agent_type)


def test_valid_dag_is_returned_keyed_by_type_in_order():
    registry = validate_registry([_spec("A"), _spec("B", "A"), _spec("C", "A", "B")])
    assert list(registry) == ["A", "B", "C"]


def test_diamond_graph_is_valid():
    registry = validate_registry([_spec("A"), _spec("B", "A"), _spec("C", "A"), _spec("D", "B", "C")])
    assert set(registry) == {"A", "B", "C", "D"}


def test_empty_registry_is_valid():
    assert validate_registry([]) == {}


def test_duplicate_agent_type_is_rejected():
    with pytest.raises(RegistryError, match="duplicate agent type: A"):
        validate_registry([_spec("A"), _spec("A")])


def test_unknown_dependency_is_rejected():
    with pytest.raises(RegistryError, match="B depends on unknown agent Z"):
        validate_registry([_spec("A"), _spec("B", "Z")])


def test_self_dependency_is_a_cycle():
    with pytest.raises(RegistryError, match="cycle"):
        validate_registry([_spec("A", "A")])


def test_two_node_cycle_is_rejected():
    with pytest.raises(RegistryError, match="cycle.*A, B"):
        validate_registry([_spec("A", "B"), _spec("B", "A")])


def test_three_node_cycle_with_a_valid_branch_names_only_the_cycle():
    with pytest.raises(RegistryError) as info:
        validate_registry([_spec("ROOT"), _spec("A", "C"), _spec("B", "A"), _spec("C", "B")])
    assert "A, B, C" in str(info.value)
    assert "ROOT" not in str(info.value)


def test_unknown_evidence_provider_is_rejected():
    spec = _spec("A")
    spec.evidence_providers = ("web_search", "crystal_ball")
    with pytest.raises(RegistryError, match="crystal_ball"):
        validate_registry([spec])


def test_known_evidence_providers_are_accepted():
    spec = _spec("A")
    spec.evidence_providers = ("market_competition", "fuel_price", "fx_rate", "dgca_market", "web_search")
    assert validate_registry([spec])["A"] is spec

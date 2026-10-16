from collections.abc import Iterable

from app.agents.cargo_agent import CARGO_AGENT_SPEC
from app.agents.crew_agent import CREW_AGENT_SPEC
from app.agents.finance_agent import FINANCE_AGENT_SPEC
from app.agents.fleet_agent import FLEET_AGENT_SPEC
from app.agents.maintenance_agent import MAINTENANCE_AGENT_SPEC
from app.agents.network_agent import NETWORK_AGENT_SPEC
from app.agents.spec import AgentSpec
from app.evidence.catalog import EVIDENCE_PROVIDERS


class RegistryError(ValueError):
    """The set of agent specs is not a valid dependency graph."""


def validate_registry(specs: Iterable[AgentSpec]) -> dict[str, AgentSpec]:
    """Key specs by agent_type (order preserved), rejecting duplicates, unknown dependencies, unknown evidence providers and cycles."""
    registry: dict[str, AgentSpec] = {}
    for spec in specs:
        if spec.agent_type in registry:
            raise RegistryError(f"duplicate agent type: {spec.agent_type}")
        registry[spec.agent_type] = spec

    for spec in registry.values():
        for dependency in spec.depends_on:
            if dependency not in registry:
                raise RegistryError(f"{spec.agent_type} depends on unknown agent {dependency}")

    for spec in registry.values():
        for provider in spec.evidence_providers:
            if provider not in EVIDENCE_PROVIDERS:
                raise RegistryError(f"{spec.agent_type} uses unknown evidence provider {provider}")

    _reject_cycles(registry)
    return registry


def _reject_cycles(registry: dict[str, AgentSpec]) -> None:
    """Kahn's algorithm: repeatedly remove agents with no unmet dependencies; leftovers form a cycle."""
    remaining = {agent_type: set(spec.depends_on) for agent_type, spec in registry.items()}
    while remaining:
        ready = [agent_type for agent_type, deps in remaining.items() if not deps]
        if not ready:
            raise RegistryError("dependency cycle among agents: " + ", ".join(sorted(remaining)))
        for agent_type in ready:
            del remaining[agent_type]
        for deps in remaining.values():
            deps.difference_update(ready)


AGENT_REGISTRY = validate_registry([NETWORK_AGENT_SPEC, MAINTENANCE_AGENT_SPEC, FLEET_AGENT_SPEC, CREW_AGENT_SPEC, CARGO_AGENT_SPEC, FINANCE_AGENT_SPEC])

"""Prompt-based evidence routing: the objective's wording decides which extra evidence providers an agent gets.

An agent always runs the providers in its own spec. On top of those, `ROUTING_TABLE` adds providers when the
objective mentions a topic (whole words, case-insensitive, a trailing "s" allowed for plurals) and the agent is
one the topic applies to. The match is deterministic: no LLM is involved, so the same objective always routes the
same way. A routed provider is skipped when it is not registered in the evidence catalog at runtime (other
workstreams add providers and agents independently) or when the agent already has it.
"""
import re
from collections.abc import Iterable
from typing import NamedTuple

from app.evidence import catalog


class Route(NamedTuple):
    topic: str
    keywords: tuple[str, ...]
    providers: tuple[str, ...]
    agents: frozenset[str]


# One row per topic: (topic, objective keywords, providers added, agents that receive them).
ROUTING_TABLE: tuple[Route, ...] = (
    Route(
        "fuel",
        ("fuel", "oil", "crude", "jet fuel", "cost"),
        ("fuel_price", "brent_price"),
        frozenset({"NETWORK", "FLEET", "CARGO", "FINANCE", "PRICING"}),
    ),
    Route(
        "currency",
        ("rupee", "inr", "dollar", "currency", "exchange rate", "forex"),
        ("fx_rate",),
        frozenset({"NETWORK", "CARGO", "FINANCE", "PRICING"}),
    ),
    Route(
        "weather",
        ("weather", "monsoon", "fog", "storm", "rain", "winter", "cyclone"),
        ("weather_observation", "weather_forecast", "weather_taf"),
        frozenset({"NETWORK", "FLEET", "CREW", "MAINTENANCE", "CARGO"}),
    ),
    Route(
        "seasonality",
        ("holiday", "festival", "diwali", "season", "peak", "demand", "tourism"),
        ("india_holidays", "world_bank_demand"),
        frozenset({"NETWORK", "CARGO", "MARKET", "PRICING"}),
    ),
    Route(
        "cargo",
        ("cargo", "freight"),
        ("world_bank_freight",),
        frozenset({"NETWORK", "CARGO", "FINANCE"}),
    ),
    Route(
        "safety",
        ("safety", "airworthiness", "directive", "maintenance", "grounded"),
        ("airworthiness_directives",),
        frozenset({"FLEET", "MAINTENANCE"}),
    ),
    Route(
        "airport",
        ("airport", "runway", "congestion", "capacity", "throughput", "slot"),
        ("airport_throughput", "airport_infrastructure"),
        frozenset({"NETWORK", "FLEET", "CARGO", "MARKET"}),
    ),
    Route(
        "competition",
        ("competition", "competitor", "rival", "market share", "fare", "price war"),
        ("market_competition",),
        frozenset({"NETWORK", "CARGO", "FINANCE", "MARKET", "PRICING"}),
    ),
    Route(
        "traffic",
        ("traffic", "congestion", "delay", "delays", "busy", "live traffic"),
        ("live_air_traffic",),
        frozenset({"NETWORK", "FLEET", "CREW", "WEATHER"}),
    ),
    Route(
        "nationwide",
        ("nationwide", "india", "network-wide", "monsoon", "cyclone"),
        ("india_weather_summary",),
        frozenset({"NETWORK", "CREW", "FLEET", "WEATHER"}),
    ),
    Route(
        "imd",
        ("imd", "warning", "nowcast", "thunderstorm", "cyclone", "heavy rain", "red alert"),
        ("imd_warnings",),
        frozenset({"WEATHER", "NETWORK"}),
    ),
    Route(
        "airport_charges",
        ("charge", "landing", "parking", "turnaround", "airport fee", "airport charge", "udf", "user development fee"),
        ("airport_charges",),
        frozenset({"NETWORK", "FINANCE", "PRICING", "FLEET"}),
    ),
)


def _pattern(keywords: tuple[str, ...]) -> re.Pattern[str]:
    words = (r"\s+".join(re.escape(part) for part in keyword.split()) for keyword in keywords)
    return re.compile(r"\b(?:" + "|".join(words) + r")s?\b", re.IGNORECASE)


_PATTERNS = {route.topic: _pattern(route.keywords) for route in ROUTING_TABLE}


def topics_in(objective: str) -> list[str]:
    """The topics (table order) whose keywords appear in the objective."""
    return [route.topic for route in ROUTING_TABLE if _PATTERNS[route.topic].search(objective or "")]


def routed_providers(agent_type: str, objective: str, existing: Iterable[str] = ()) -> list[dict[str, str]]:
    """The extra providers for this agent and objective, as [{"provider": ..., "topic": ...}] in table order.

    Each provider appears once (the first topic that asks for it). Providers in `existing` and providers not
    registered in the evidence catalog are left out.
    """
    skip = set(existing)
    routed: list[dict[str, str]] = []
    for route in ROUTING_TABLE:
        if agent_type not in route.agents or not _PATTERNS[route.topic].search(objective or ""):
            continue
        for provider in route.providers:
            if provider in skip or provider not in catalog.EVIDENCE_PROVIDERS:
                continue
            skip.add(provider)
            routed.append({"provider": provider, "topic": route.topic})
    return routed


def extra_providers_for(agent_type: str, objective: str, existing: Iterable[str] = ()) -> tuple[str, ...]:
    """Provider names to run in addition to the agent's own (see `routed_providers`)."""
    return tuple(entry["provider"] for entry in routed_providers(agent_type, objective, existing))

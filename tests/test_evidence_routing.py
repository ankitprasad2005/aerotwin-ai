import pytest

from app.evidence import catalog
from app.evidence.routing import ROUTING_TABLE, extra_providers_for, routed_providers, topics_in

ALL_PROVIDERS = {p for route in ROUTING_TABLE for p in route.providers}


@pytest.fixture(autouse=True)
def full_catalog(monkeypatch):
    async def noop(db, request):
        return []

    monkeypatch.setattr(catalog, "EVIDENCE_PROVIDERS", {name: noop for name in ALL_PROVIDERS})


def test_table_shape():
    assert [r.topic for r in ROUTING_TABLE] == [
        "fuel", "currency", "weather", "seasonality", "cargo", "safety", "airport", "competition", "traffic"
    ]
    fuel = ROUTING_TABLE[0]
    assert fuel.providers == ("fuel_price", "brent_price")
    assert fuel.agents == {"NETWORK", "FLEET", "CARGO", "FINANCE", "PRICING"}


@pytest.mark.parametrize(
    "objective,topic",
    [
        ("Cut jet fuel burn", "fuel"),
        ("crude is spiking", "fuel"),
        ("reduce COST", "fuel"),
        ("a weaker rupee", "currency"),
        ("watch the exchange   rate", "currency"),
        ("monsoon disruption", "weather"),
        ("handle fog and cyclone risk", "weather"),
        ("Diwali demand", "seasonality"),
        ("more freight capacity", "cargo"),
        ("any open directive?", "safety"),
        ("fight a price war", "competition"),
        ("grow market share", "competition"),
    ],
)
def test_keywords_match(objective, topic):
    assert topic in topics_in(objective)


@pytest.mark.parametrize(
    "objective",
    ["Improve profitability", "", "a coil of foil", "boilerplate", "doilies", "hundred", "pricewar", "fairness", "forexample"],
)
def test_word_boundaries_prevent_partial_matches(objective):
    assert topics_in(objective) == []


def test_plural_forms_match_and_case_is_ignored():
    assert topics_in("STORMS, RIVALS and FARES") == ["weather", "competition"]


def test_multiple_topics_follow_table_order():
    assert topics_in("fog will hurt fuel costs and the rupee") == ["fuel", "currency", "weather"]


def test_extra_providers_respect_the_agent_scope():
    assert extra_providers_for("CREW", "fuel and weather") == ("weather_observation", "weather_forecast", "weather_taf")
    assert extra_providers_for("NETWORK", "fuel and weather")[:2] == ("fuel_price", "brent_price")
    assert extra_providers_for("EMISSIONS", "fuel weather rupee cargo") == ()
    assert extra_providers_for("UNKNOWN", "fuel") == ()
    assert extra_providers_for("CREW", "Improve profitability") == ()


def test_no_topic_adds_nothing():
    for agent in ("NETWORK", "FLEET", "CREW", "FINANCE", "WEATHER"):
        assert extra_providers_for(agent, "Improve profitability") == ()


def test_existing_providers_are_skipped():
    assert extra_providers_for("FINANCE", "fuel", existing=("fuel_price", "web_search")) == ("brent_price",)


def test_unregistered_providers_are_skipped(monkeypatch):
    monkeypatch.setattr(catalog, "EVIDENCE_PROVIDERS", {"weather_forecast": None})
    assert extra_providers_for("CREW", "weather") == ("weather_forecast",)
    assert extra_providers_for("PRICING", "fuel rupee") == ()


def test_a_provider_asked_for_by_two_topics_is_listed_once_with_the_first_topic():
    entries = routed_providers("NETWORK", "fuel, rivals and cargo")
    names = [e["provider"] for e in entries]
    assert len(names) == len(set(names))
    assert {"provider": "market_competition", "topic": "competition"} in entries
    assert {"provider": "fuel_price", "topic": "fuel"} in entries
    assert {"provider": "world_bank_freight", "topic": "cargo"} in entries


@pytest.mark.parametrize("word", ["traffic", "delay", "busy", "live traffic"])
def test_traffic_topic_routes_live_air_traffic(word):
    assert topics_in(f"check the {word} situation") == ["traffic"]
    for agent in ("NETWORK", "FLEET", "CREW", "WEATHER"):
        assert extra_providers_for(agent, f"check the {word} situation") == ("live_air_traffic",)
    assert extra_providers_for("FINANCE", f"check the {word} situation") == ()


@pytest.mark.parametrize(
    "objective",
    ["Is Mumbai airport congested?", "runway capacity at BOM", "check slot availability", "airport throughput trend"],
)
def test_airport_keywords_route_to_both_airport_providers(objective):
    assert "airport" in topics_in(objective)
    for agent in ("NETWORK", "FLEET", "CARGO", "MARKET"):
        assert extra_providers_for(agent, objective) == ("airport_throughput", "airport_infrastructure")


def test_airport_providers_are_not_routed_to_other_agents_or_when_the_agent_has_them():
    assert extra_providers_for("CREW", "runway capacity") == ()
    assert extra_providers_for("FINANCE", "airport slots") == ()
    assert extra_providers_for("FLEET", "runway length", existing=("airport_infrastructure",)) == ("airport_throughput",)
    assert routed_providers("MARKET", "airport", existing=("airport_throughput",)) == [
        {"provider": "airport_infrastructure", "topic": "airport"}
    ]

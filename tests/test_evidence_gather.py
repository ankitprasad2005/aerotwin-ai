import asyncio
import json
import logging

import pytest
from sqlalchemy import text

from app.agents.spec import AgentSpec
from app.config import get_settings
from app.evidence import catalog
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.gather import gather_evidence


def make_item(item_id: str, reliability: float = 0.5, content="x") -> EvidenceItem:
    return EvidenceItem(
        id=item_id, source="web", kind="web", title=f"title {item_id}", url=None, fetched_at=None,
        reliability=reliability, content=content,
    )


async def _tool(db):
    return {"entities": []}


def make_spec(*providers: str) -> AgentSpec:
    from app.agents.schemas import NetworkRecommendation

    return AgentSpec(
        agent_type="X", task_description="t", system_instructions="s", tool_name="tool", tool_fn=_tool,
        output_schema=NetworkRecommendation, evidence_providers=tuple(providers),
    )


@pytest.fixture
def providers(monkeypatch):
    """An isolated provider catalog the test can fill."""
    registry: dict = {}
    monkeypatch.setattr(catalog, "EVIDENCE_PROVIDERS", registry)
    return registry


@pytest.fixture
def limits(monkeypatch):
    def apply(**overrides):
        settings = get_settings()
        for name, value in overrides.items():
            monkeypatch.setattr(settings, name, value)
    return apply


async def run(db, *names, previous_results=None):
    return await gather_evidence(db, spec=make_spec(*names), objective="obj", previous_results=previous_results or [])


async def test_no_providers_returns_empty(db_session, providers):
    assert await run(db_session) == ([], [])


async def test_items_are_returned_as_json_dicts(db_session, providers):
    async def p(db, request):
        return [make_item("a", 0.9, {"k": 1})]

    providers["p"] = p
    items, unavailable = await run(db_session, "p")
    assert unavailable == []
    assert items == [make_item("a", 0.9, {"k": 1}).model_dump(mode="json")]
    json.dumps(items)  # plain JSON types only


async def test_provider_receives_request_with_route_from_network_result(db_session, providers):
    seen = []

    async def p(db, request: EvidenceRequest):
        seen.append(request)
        return []

    providers["p"] = p
    previous = [
        {"agent_type": "FLEET", "route": "ZZZ-YYY"},
        {"agent_type": "NETWORK", "route": "BOM-DEL", "action": "INCREASE_FREQUENCY"},
        {"agent_type": "NETWORK", "route": "LATER-ONE"},
    ]
    await run(db_session, "p", previous_results=previous)
    assert seen[0].route == "BOM-DEL"
    assert seen[0].agent_type == "X"
    assert seen[0].objective == "obj"
    assert seen[0].previous_results == previous


@pytest.mark.parametrize(
    "previous",
    [[], [{"agent_type": "FLEET", "route": "BOM-DEL"}], [{"agent_type": "NETWORK"}], [{"agent_type": "NETWORK", "route": None}]],
)
async def test_route_is_none_without_a_network_route(db_session, providers, previous):
    seen = []

    async def p(db, request):
        seen.append(request.route)
        return []

    providers["p"] = p
    await run(db_session, "p", previous_results=previous)
    assert seen == [None]


async def test_provider_exception_is_reported_not_raised(db_session, providers, caplog):
    async def bad(db, request):
        raise RuntimeError("boom")

    async def good(db, request):
        return [make_item("ok")]

    providers["bad"], providers["good"] = bad, good
    with caplog.at_level(logging.WARNING):
        items, unavailable = await run(db_session, "bad", "good")
    assert [i["id"] for i in items] == ["ok"]
    assert len(unavailable) == 1 and unavailable[0].startswith("bad: ") and "boom" in unavailable[0]
    assert any("bad" in r.message and r.levelno == logging.WARNING for r in caplog.records)


async def test_unknown_provider_name_is_reported_not_raised(db_session, providers):
    items, unavailable = await run(db_session, "nope")
    assert items == [] and unavailable == ["nope: unknown provider"]


async def test_long_error_messages_are_truncated(db_session, providers):
    async def bad(db, request):
        raise RuntimeError("x" * 5000)

    providers["bad"] = bad
    _, unavailable = await run(db_session, "bad")
    assert len(unavailable[0]) < 300


async def test_timeout_is_reported_and_other_providers_still_run(db_session, providers, limits):
    limits(evidence_provider_timeout_seconds=0.05)

    async def slow(db, request):
        await asyncio.sleep(5)
        return [make_item("never")]

    async def good(db, request):
        return [make_item("ok")]

    providers["slow"], providers["good"] = slow, good
    items, unavailable = await run(db_session, "slow", "good")
    assert [i["id"] for i in items] == ["ok"]
    assert len(unavailable) == 1 and unavailable[0].startswith("slow: ") and "timed out" in unavailable[0]


async def test_failed_sql_statement_does_not_poison_the_session(db_session, providers):
    async def bad_sql(db, request):
        await db.execute(text("SELECT * FROM table_that_does_not_exist"))
        return []

    async def good(db, request):
        value = (await db.execute(text("SELECT 41 + 1"))).scalar_one()
        return [make_item(f"v{value}")]

    providers["bad_sql"], providers["good"] = bad_sql, good
    items, unavailable = await run(db_session, "bad_sql", "good")
    assert [i["id"] for i in items] == ["v42"]
    assert unavailable[0].startswith("bad_sql: ")
    # The agent's own transaction is still usable afterwards.
    assert (await db_session.execute(text("SELECT 1"))).scalar_one() == 1


async def test_timeout_during_a_query_leaves_the_session_usable(db_session, providers, limits):
    limits(evidence_provider_timeout_seconds=0.2)

    async def slow_sql(db, request):
        await db.execute(text("SELECT pg_sleep(5)"))
        return []

    providers["slow_sql"] = slow_sql
    _, unavailable = await run(db_session, "slow_sql")
    assert "timed out" in unavailable[0]
    assert (await db_session.execute(text("SELECT 1"))).scalar_one() == 1


async def test_duplicate_ids_across_providers_are_collapsed_keeping_first(db_session, providers):
    async def one(db, request):
        return [make_item("dup", 0.5, "first"), make_item("a", 0.5)]

    async def two(db, request):
        return [make_item("dup", 0.9, "second"), make_item("dup", 0.9, "third")]

    providers["one"], providers["two"] = one, two
    items, _ = await run(db_session, "one", "two")
    assert sorted(i["id"] for i in items) == ["a", "dup"]
    assert next(i for i in items if i["id"] == "dup")["content"] == "first"


async def test_items_are_sorted_by_reliability_descending_and_stable(db_session, providers):
    async def p(db, request):
        return [make_item("low", 0.4), make_item("mid1", 0.7), make_item("high", 0.95), make_item("mid2", 0.7)]

    providers["p"] = p
    items, _ = await run(db_session, "p")
    assert [i["id"] for i in items] == ["high", "mid1", "mid2", "low"]


async def test_item_cap_keeps_the_most_reliable(db_session, providers, limits):
    limits(evidence_max_items_per_agent=2)

    async def p(db, request):
        return [make_item("c", 0.3), make_item("a", 0.9), make_item("b", 0.6)]

    providers["p"] = p
    items, _ = await run(db_session, "p")
    assert [i["id"] for i in items] == ["a", "b"]


async def test_zero_item_cap_returns_no_items(db_session, providers, limits):
    limits(evidence_max_items_per_agent=0)

    async def p(db, request):
        return [make_item("a")]

    providers["p"] = p
    assert (await run(db_session, "p"))[0] == []


async def test_char_cap_stops_adding_once_exceeded(db_session, providers, limits):
    one = len(json.dumps(make_item("a", 0.9, "y" * 100).model_dump(mode="json")))
    limits(evidence_max_chars_per_agent=500)  # the minimum allowed; sized below via padding
    size = one

    async def p(db, request):
        # Each ~size chars; 500 // size items fit.
        return [make_item(f"i{n}", (9 - n) / 10, "y" * 100) for n in range(10)]

    providers["p"] = p
    items, _ = await run(db_session, "p")
    expected = 500 // size
    assert 0 < expected < 10
    assert len(items) == expected
    assert sum(len(json.dumps(i)) for i in items) <= 500
    assert [i["id"] for i in items] == [f"i{n}" for n in range(expected)]


async def test_char_cap_exact_boundary_is_inclusive(db_session, providers, limits):
    item = make_item("a", 0.9, "y" * 100)
    size = len(json.dumps(item.model_dump(mode="json")))
    limits(evidence_max_chars_per_agent=max(500, size), evidence_max_items_per_agent=50)

    async def p(db, request):
        return [item]

    providers["p"] = p
    items, _ = await run(db_session, "p")
    assert len(items) == 1


async def test_single_oversized_item_is_dropped_not_truncated(db_session, providers, limits):
    limits(evidence_max_chars_per_agent=500)

    async def p(db, request):
        return [make_item("huge", 0.9, "z" * 2000), make_item("small", 0.5, "ok")]

    providers["p"] = p
    items, _ = await run(db_session, "p")
    # The cap stops at the first item that does not fit, so the lower-reliability small one is not
    # promoted past it.
    assert items == []


async def test_provider_returning_nothing_is_fine(db_session, providers):
    async def p(db, request):
        return []

    providers["p"] = p
    assert await run(db_session, "p") == ([], [])


async def test_a_busy_high_reliability_provider_cannot_starve_the_others(db_session, providers, limits):
    limits(evidence_max_items_per_agent=8)

    async def market(db, request):
        return [make_item(f"m{n}", 0.7) for n in range(6)]

    async def web(db, request):
        return [make_item(f"w{n}", 0.4) for n in range(5)]

    async def fuel(db, request):
        return [make_item("fuel", 0.9)]

    providers["market"], providers["web"], providers["fuel"] = market, web, fuel
    items, _ = await run(db_session, "market", "web", "fuel")

    ids = [i["id"] for i in items]
    assert len(ids) == 8
    assert sum(i.startswith("w") for i in ids) >= 3  # the web gets its share, not the leftovers
    assert ids[0] == "fuel"  # the result is still ordered most reliable first
    assert [i["reliability"] for i in items] == sorted((i["reliability"] for i in items), reverse=True)


async def test_an_oversized_item_only_closes_its_own_provider(db_session, providers, limits):
    limits(evidence_max_chars_per_agent=500)

    async def big(db, request):
        return [make_item("huge", 0.9, "z" * 2000), make_item("big_small", 0.8, "ok")]

    async def other(db, request):
        return [make_item("other", 0.5, "ok")]

    providers["big"], providers["other"] = big, other
    items, _ = await run(db_session, "big", "other")
    assert [i["id"] for i in items] == ["other"]


async def test_routed_extras_run_alongside_the_agents_own_providers(db_session, providers):
    from app.evidence.routing import ROUTING_TABLE

    seen = []

    def make(name, reliability):
        async def p(db, request):
            seen.append(name)
            return [make_item(f"{name}:1", reliability), make_item(f"{name}:2", reliability)]
        return p

    providers["own"] = make("own", 0.5)
    providers["fuel_price"] = make("fuel_price", 0.9)
    providers["brent_price"] = make("brent_price", 0.9)
    assert ROUTING_TABLE[0].providers[:2] == ("fuel_price", "brent_price")
    spec = make_spec("own")
    spec.agent_type = "FINANCE"

    items, unavailable = await gather_evidence(db_session, spec=spec, objective="jet fuel cost", previous_results=[])

    assert seen == ["own", "fuel_price", "brent_price"] and unavailable == []
    assert len(items) == 6


async def test_routed_extras_share_the_caps_and_never_double_run_own_providers(db_session, providers, limits):
    limits(evidence_max_items_per_agent=4)
    calls = []

    def make(name):
        async def p(db, request):
            calls.append(name)
            return [make_item(f"{name}:{i}", 0.5) for i in range(5)]
        return p

    for name in ("own", "fuel_price", "brent_price"):
        providers[name] = make(name)
    spec = make_spec("own", "fuel_price")
    spec.agent_type = "FINANCE"

    items, _ = await gather_evidence(db_session, spec=spec, objective="fuel", previous_results=[])

    assert calls == ["own", "fuel_price", "brent_price"]
    prefixes = [i["id"].split(":")[0] for i in items]
    assert len(items) == 4 and set(prefixes) == {"own", "fuel_price", "brent_price"}


async def test_a_failing_routed_extra_is_reported_and_unregistered_extras_are_skipped(db_session, providers):
    async def boom(db, request):
        raise RuntimeError("down")

    providers["weather_forecast"] = boom  # weather_observation / weather_taf are not registered here
    spec = make_spec()
    spec.agent_type = "CREW"

    items, unavailable = await gather_evidence(db_session, spec=spec, objective="monsoon", previous_results=[])

    assert items == [] and unavailable == ["weather_forecast: RuntimeError: down"]


async def test_no_topic_runs_no_extras(db_session, providers):
    async def p(db, request):
        raise AssertionError("must not run")

    providers["fuel_price"] = p
    spec = make_spec()
    spec.agent_type = "FINANCE"
    assert await gather_evidence(db_session, spec=spec, objective="Improve profitability", previous_results=[]) == ([], [])

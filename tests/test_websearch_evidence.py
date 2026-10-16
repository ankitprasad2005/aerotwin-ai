import asyncio
import time
import hashlib
from datetime import datetime, timezone

import pytest
import respx
from sqlalchemy import func, select

from app.config import Settings
from app.evidence.base import EvidenceRequest
from app.models.external import WebSearchCache
from app.websearch import evidence
from app.websearch.client import WebSearchError
from app.websearch.evidence import build_query, item_id, objective_keywords, web_search
from app.websearch.service import build_client, is_active, is_configured

BASE = "http://searx.test"
NOW = datetime(2027, 3, 1, tzinfo=timezone.utc)


def req(agent="NETWORK", objective="Improve profitability", route=None):
    return EvidenceRequest(agent_type=agent, objective=objective, route=route)


def settings(**kw):
    kw.setdefault("searxng_url", BASE)
    return Settings(_env_file=None, **kw)


@pytest.fixture
def use_settings(monkeypatch):
    def _use(**kw):
        s = settings(**kw)
        monkeypatch.setattr(evidence, "get_settings", lambda: s)
        return s
    return _use


# --- service --------------------------------------------------------------------------------------

def test_service_flags():
    assert is_configured(settings()) and is_active(settings())
    assert not is_configured(settings(searxng_url=None))
    assert not is_configured(settings(searxng_url="   "))
    assert not is_active(settings(web_search_enabled=False))


def test_build_client_none_when_inactive_and_timeout_override():
    assert build_client(settings(searxng_url=None)) is None
    assert build_client(settings(web_search_enabled=False)) is None
    assert build_client(settings(), timeout=2.0)._timeout == 2.0
    assert build_client(settings(web_search_timeout_seconds=3.0))._timeout == 3.0


# --- query templates ------------------------------------------------------------------------------

@pytest.mark.parametrize("agent,route,expected", [
    ("NETWORK", "DEL-BOM", "DEL BOM air traffic demand India 2027"),
    ("CARGO", "BOM-DEL", "BOM DEL air cargo demand India 2027"),
    ("FLEET", "DEL-BOM", "A320 aircraft availability India airline 2027"),
    ("MAINTENANCE", "DEL-BOM", "A320 maintenance check delays India 2027"),
    ("CREW", None, "India airline pilot crew shortage 2027"),
    ("WEATHER", "BOM-DEL", "BOM DEL flight delays weather India 2027"),
])
def test_query_templates_with_route(agent, route, expected):
    assert build_query(req(agent, route=route), now=NOW) == expected


@pytest.mark.parametrize("agent,expected", [
    ("NETWORK", "Grow Hyderabad Chennai traffic air traffic demand India 2027"),
    ("CARGO", "Grow Hyderabad Chennai traffic air cargo demand India 2027"),
])
def test_route_templates_fall_back_to_objective_keywords(agent, expected):
    out = build_query(req(agent, objective="Grow the Hyderabad Chennai traffic for the airline"), now=NOW)
    assert out == expected


def test_fleet_uses_aircraft_from_objective():
    assert build_query(req("FLEET", objective="Do we have enough b737 or A321neo?"), now=NOW) == (
        "B737 aircraft availability India airline 2027")
    assert build_query(req("FLEET", objective="plan ATR 72 growth"), now=NOW).startswith("ATR 72 aircraft")


def test_empty_route_and_objective_still_yield_a_clean_query():
    assert build_query(req("NETWORK", objective="the and for", route="--"), now=NOW) == "air traffic demand India 2027"


def test_unknown_agent_has_no_query():
    assert build_query(req("SOMETHING"), now=NOW) is None


def test_year_comes_from_the_injectable_clock(monkeypatch):
    monkeypatch.setattr(evidence, "_utcnow", lambda: datetime(2031, 1, 1, tzinfo=timezone.utc))
    assert build_query(req("CREW")).endswith("2031")
    assert build_query(req("CREW"), now=NOW).endswith("2027")


def test_query_is_capped_and_route_is_sanitised():
    q = build_query(req("NETWORK", route="<script>x</script>" * 40), now=NOW)
    assert len(q) <= 200 and "<" not in q and ">" not in q


def test_objective_keywords_caps_and_filters():
    assert objective_keywords("a an of to") == ""
    assert objective_keywords("one1 two2 three3 four4 five5 six66 seven7") == "one1 two2 three3 four4 five5"


# --- provider -------------------------------------------------------------------------------------

def hits(n):
    return {"results": [{"url": f"https://a.example/{i}", "title": f"T{i}", "content": f"S{i}", "engine": "ddg"}
                        for i in range(n)]}


@respx.mock
async def test_provider_builds_items(db_session, use_settings, monkeypatch):
    monkeypatch.setattr(evidence, "_utcnow", lambda: datetime(2026, 10, 15, tzinfo=timezone.utc))
    use_settings()
    route = respx.get(f"{BASE}/search").respond(json=hits(2))
    items = await web_search(db_session, req("CREW"))
    assert len(items) == 2
    first = items[0]
    assert first.id == "web:" + hashlib.sha1(b"https://a.example/0").hexdigest()[:8] == item_id("https://a.example/0")
    assert (first.source, first.kind, first.reliability) == ("web", "web", 0.4)
    assert first.title == "T0" and first.url == "https://a.example/0" and first.fetched_at is not None
    assert first.content == {"snippet": "S0", "engine": "ddg", "query": "India airline pilot crew shortage 2026"}
    assert route.calls.last.request.url.params["q"] == "india airline pilot crew shortage 2026"
    


@respx.mock
async def test_provider_second_call_hits_cache(db_session, use_settings):
    use_settings()
    route = respx.get(f"{BASE}/search").respond(json=hits(1))
    await web_search(db_session, req("CREW"))
    await web_search(db_session, req("CREW"))
    assert route.call_count == 1


@respx.mock
async def test_provider_caps_to_max_results(db_session, use_settings):
    use_settings(web_search_max_results=2)
    respx.get(f"{BASE}/search").respond(json=hits(9))
    assert len(await web_search(db_session, req("CREW"))) == 2


@respx.mock
async def test_provider_title_falls_back_to_url(db_session, use_settings):
    use_settings()
    respx.get(f"{BASE}/search").respond(json={"results": [{"url": "https://a.example/z"}]})
    assert (await web_search(db_session, req("CREW")))[0].title == "https://a.example/z"


@respx.mock
async def test_provider_flags_stale_results_when_refresh_fails(db_session, use_settings):
    use_settings(web_search_cache_ttl_hours=0.0001)
    respx.get(f"{BASE}/search").respond(json=hits(1))
    await web_search(db_session, req("CREW"))
    row = (await db_session.execute(select(WebSearchCache))).scalar_one()
    row.fetched_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    await db_session.flush()
    respx.get(f"{BASE}/search").respond(500)
    items = await web_search(db_session, req("CREW"))
    assert items[0].content["stale"] is True


@respx.mock
async def test_provider_raises_when_search_fails_without_cache(db_session, use_settings):
    use_settings()
    respx.get(f"{BASE}/search").respond(500)
    with pytest.raises(WebSearchError):
        await web_search(db_session, req("CREW"))


async def _count(db):
    return (await db.execute(select(func.count()).select_from(WebSearchCache))).scalar_one()


@respx.mock
async def test_provider_empty_when_disabled_or_unconfigured(db_session, use_settings):
    route = respx.get(f"{BASE}/search").respond(json=hits(1))
    use_settings(web_search_enabled=False)
    assert await web_search(db_session, req("CREW")) == []
    use_settings(searxng_url=None)
    assert await web_search(db_session, req("CREW")) == []
    assert route.call_count == 0 and await _count(db_session) == 0


@respx.mock
async def test_provider_empty_for_agent_without_template(db_session, use_settings):
    use_settings()
    route = respx.get(f"{BASE}/search").respond(json=hits(1))
    assert await web_search(db_session, req("SOMETHING")) == []
    assert route.call_count == 0


@respx.mock
async def test_provider_uses_real_settings_by_default(db_session, monkeypatch):
    monkeypatch.setattr(evidence, "get_settings", lambda: settings(searxng_url=None))
    assert await web_search(db_session, req("CREW")) == []


class _SlowClient:
    async def search(self, query):
        await asyncio.sleep(30)


async def _stale_row(db, query="india airline pilot crew shortage 2026"):
    db.add(WebSearchCache(
        query=query, results=[{"url": "https://old.example/1", "title": "Old", "snippet": "S", "engine": "ddg"}],
        result_count=1, fetched_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    ))
    await db.flush()


async def test_slow_searxng_degrades_to_the_stale_cache_within_the_provider_timeout(db_session, use_settings, monkeypatch):
    monkeypatch.setattr(evidence, "_utcnow", lambda: datetime(2026, 10, 15, tzinfo=timezone.utc))
    use_settings(evidence_provider_timeout_seconds=1.0)
    monkeypatch.setattr(evidence, "build_client", lambda s: _SlowClient())
    await _stale_row(db_session)
    started = time.monotonic()

    items = await asyncio.wait_for(web_search(db_session, req("CREW")), timeout=1.0)

    assert time.monotonic() - started < 1.0
    assert [i.url for i in items] == ["https://old.example/1"]
    assert items[0].content["stale"] is True


async def test_gather_reports_stale_web_results_not_a_timeout(db_session, use_settings, monkeypatch):
    import app.evidence.gather as gather
    from dataclasses import replace
    from tests.test_evidence_gather import make_spec

    monkeypatch.setattr(evidence, "_utcnow", lambda: datetime(2026, 10, 15, tzinfo=timezone.utc))
    s = use_settings(evidence_provider_timeout_seconds=1.0)
    monkeypatch.setattr(gather, "get_settings", lambda: s)
    monkeypatch.setattr(evidence, "build_client", lambda s: _SlowClient())
    await _stale_row(db_session)

    items, unavailable = await gather.gather_evidence(
        db_session, spec=replace(make_spec("web_search"), agent_type="CREW"), objective="x", previous_results=[],
    )

    assert unavailable == []
    assert [i["url"] for i in items] == ["https://old.example/1"]


async def test_slow_searxng_without_a_cache_entry_is_an_error_not_a_hang(db_session, use_settings, monkeypatch):
    use_settings(evidence_provider_timeout_seconds=1.0)
    monkeypatch.setattr(evidence, "build_client", lambda s: _SlowClient())
    with pytest.raises(WebSearchError):
        await asyncio.wait_for(web_search(db_session, req("CREW")), timeout=1.0)

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.web_search import router
from app.config import Settings, get_settings
from app.models.external import WebSearchCache

BASE = "http://searx.test"


def make_client(db_session, **kw) -> AsyncClient:
    kw.setdefault("searxng_url", BASE)
    settings = Settings(_env_file=None, **kw)
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def hits(n=2):
    return {"results": [{"url": f"https://a.example/{i}", "title": f"T{i}", "content": f"S{i}", "engine": "ddg"}
                        for i in range(n)]}


# --- status ---------------------------------------------------------------------------------------

@respx.mock
async def test_status_reachable(db_session):
    respx.get(f"{BASE}/healthz").respond(200)
    async with make_client(db_session) as c:
        r = await c.get("/api/web-search/status")
    assert r.status_code == 200
    assert r.json() == {"enabled": True, "configured": True, "reachable": True}


@respx.mock
async def test_status_unreachable(db_session):
    respx.get(f"{BASE}/healthz").mock(side_effect=httpx.ConnectError("down"))
    async with make_client(db_session) as c:
        r = await c.get("/api/web-search/status")
    assert r.json() == {"enabled": True, "configured": True, "reachable": False}


@respx.mock
async def test_status_unconfigured_does_not_ping(db_session):
    route = respx.get(f"{BASE}/healthz").respond(200)
    async with make_client(db_session, searxng_url=None) as c:
        r = await c.get("/api/web-search/status")
    assert r.json() == {"enabled": True, "configured": False, "reachable": False}
    assert route.call_count == 0


@respx.mock
async def test_status_disabled_does_not_ping(db_session):
    route = respx.get(f"{BASE}/healthz").respond(200)
    async with make_client(db_session, web_search_enabled=False) as c:
        r = await c.get("/api/web-search/status")
    assert r.json() == {"enabled": False, "configured": True, "reachable": False}
    assert route.call_count == 0


# --- POST -----------------------------------------------------------------------------------------

@respx.mock
async def test_post_searches_then_serves_from_cache(db_session):
    route = respx.get(f"{BASE}/search").respond(json=hits())
    async with make_client(db_session) as c:
        first = await c.post("/api/web-search", json={"query": "  Delhi   Mumbai  "})
        second = await c.post("/api/web-search", json={"query": "delhi mumbai"})
    body = first.json()
    assert first.status_code == 200
    assert body["query"] == "delhi mumbai" and body["cached"] is False and body["stale"] is False
    assert [x["url"] for x in body["results"]] == ["https://a.example/0", "https://a.example/1"]
    assert set(body["results"][0]) == {"title", "url", "snippet", "engine"}
    assert second.json()["cached"] is True
    assert route.call_count == 1


@respx.mock
async def test_post_accepts_exactly_200_chars(db_session):
    respx.get(f"{BASE}/search").respond(json=hits(1))
    async with make_client(db_session) as c:
        r = await c.post("/api/web-search", json={"query": "x" * 200})
    assert r.status_code == 200


@pytest.mark.parametrize("body", [
    {"query": ""}, {"query": "   "}, {"query": "\n\t"}, {"query": "x" * 201}, {}, {"query": None}, {"query": 5},
])
async def test_post_validation_rejects(db_session, body):
    async with make_client(db_session) as c:
        r = await c.post("/api/web-search", json=body)
    assert r.status_code == 422


async def test_post_201_chars_after_strip_is_rejected(db_session):
    async with make_client(db_session) as c:
        too_long = await c.post("/api/web-search", json={"query": "  " + "x" * 201})
    assert too_long.status_code == 422


@respx.mock
async def test_post_503_when_disabled_or_unconfigured(db_session):
    async with make_client(db_session, web_search_enabled=False) as c:
        assert (await c.post("/api/web-search", json={"query": "q"})).status_code == 503
    async with make_client(db_session, searxng_url=None) as c:
        assert (await c.post("/api/web-search", json={"query": "q"})).status_code == 503


@respx.mock
async def test_post_502_when_search_fails_without_cache(db_session):
    respx.get(f"{BASE}/search").respond(500)
    async with make_client(db_session) as c:
        r = await c.post("/api/web-search", json={"query": "q"})
    assert r.status_code == 502 and "Web search failed" in r.json()["detail"]


@respx.mock
async def test_post_serves_stale_when_refresh_fails(db_session):
    db_session.add(WebSearchCache(
        query="q", results=[{"title": "t", "url": "https://old.example/", "snippet": "s", "engine": "e"}],
        result_count=1, fetched_at=datetime.now(timezone.utc) - timedelta(days=3)))
    await db_session.flush()
    respx.get(f"{BASE}/search").respond(500)
    async with make_client(db_session) as c:
        r = await c.post("/api/web-search", json={"query": "q"})
    assert r.status_code == 200
    assert r.json()["stale"] is True and r.json()["cached"] is True
    assert r.json()["results"][0]["url"] == "https://old.example/"


# --- cache list -----------------------------------------------------------------------------------

def _row(query, age_hours, n=1):
    return WebSearchCache(
        query=query, result_count=n, fetched_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
        results=[{"title": "t", "url": f"https://a.example/{i}", "snippet": "s", "engine": "e"} for i in range(n)])


async def test_cache_list_newest_first_and_limit(db_session):
    db_session.add_all([_row("old", 10), _row("new", 1, n=2), _row("mid", 5)])
    await db_session.flush()
    async with make_client(db_session) as c:
        r = await c.get("/api/web-search/cache")
        limited = await c.get("/api/web-search/cache", params={"limit": 2})
    assert [e["query"] for e in r.json()] == ["new", "mid", "old"]
    assert r.json()[0]["result_count"] == 2 and len(r.json()[0]["results"]) == 2
    assert [e["query"] for e in limited.json()] == ["new", "mid"]


async def test_cache_list_empty(db_session):
    async with make_client(db_session) as c:
        assert (await c.get("/api/web-search/cache")).json() == []


@pytest.mark.parametrize("limit,code", [(0, 422), (-1, 422), (201, 422), ("abc", 422), (1, 200), (200, 200)])
async def test_cache_limit_bounds(db_session, limit, code):
    async with make_client(db_session) as c:
        r = await c.get("/api/web-search/cache", params={"limit": limit})
    assert r.status_code == code

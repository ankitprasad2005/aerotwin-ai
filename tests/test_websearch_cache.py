from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.external import WebSearchCache
from app.websearch.cache import cached_search, normalise_query
from app.websearch.client import WebResult, WebSearchError

T0 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.queries: list[str] = []

    async def search(self, query):
        self.queries.append(query)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def res(n=1):
    return [WebResult(f"t{i}", f"https://a.example/{i}", "s", "e") for i in range(n)]


async def count(db):
    return (await db.execute(select(func.count()).select_from(WebSearchCache))).scalar_one()


def test_normalise_query():
    assert normalise_query("  DEL   Bom\tDemand ") == "del bom demand"
    assert normalise_query("   ") == ""


async def test_miss_fetches_and_stores(db_session):
    client = FakeClient(res(2))
    out = await cached_search(db_session, "DEL  BOM", client=client, ttl_hours=24, now=T0)
    assert (out.cached, out.stale, out.query, out.fetched_at) == (False, False, "del bom", T0)
    assert len(out.results) == 2 and out.results[0]["url"] == "https://a.example/0"
    assert client.queries == ["del bom"]
    row = (await db_session.execute(select(WebSearchCache))).scalar_one()
    assert row.result_count == 2 and row.query == "del bom"


async def test_hit_within_ttl_skips_the_network(db_session):
    client = FakeClient(res(1))
    await cached_search(db_session, "q", client=client, ttl_hours=24, now=T0)
    out = await cached_search(db_session, " Q ", client=client, ttl_hours=24, now=T0 + timedelta(hours=23))
    assert (out.cached, out.stale) == (True, False)
    assert client.queries == ["q"]


async def test_stale_entry_is_refreshed_in_place(db_session):
    client = FakeClient(res(1), res(3))
    await cached_search(db_session, "q", client=client, ttl_hours=24, now=T0)
    later = T0 + timedelta(hours=24)  # exactly at the TTL counts as expired
    out = await cached_search(db_session, "q", client=client, ttl_hours=24, now=later)
    assert (out.cached, out.stale, out.fetched_at) == (False, False, later)
    assert len(out.results) == 3
    assert await count(db_session) == 1
    row = (await db_session.execute(select(WebSearchCache))).scalar_one()
    assert row.result_count == 3 and row.fetched_at == later


async def test_stale_served_when_refresh_fails(db_session):
    client = FakeClient(res(2), WebSearchError("down"))
    await cached_search(db_session, "q", client=client, ttl_hours=1, now=T0)
    out = await cached_search(db_session, "q", client=client, ttl_hours=1, now=T0 + timedelta(hours=5))
    assert (out.cached, out.stale, out.fetched_at) == (True, True, T0)
    assert len(out.results) == 2


async def test_failure_without_entry_raises_and_stores_nothing(db_session):
    client = FakeClient(WebSearchError("down"))
    with pytest.raises(WebSearchError):
        await cached_search(db_session, "q", client=client, ttl_hours=1, now=T0)
    assert await count(db_session) == 0


async def test_empty_results_are_cached(db_session):
    client = FakeClient([])
    await cached_search(db_session, "q", client=client, ttl_hours=1, now=T0)
    out = await cached_search(db_session, "q", client=client, ttl_hours=1, now=T0)
    assert out.cached and out.results == []


async def test_default_clock_is_used(db_session):
    out = await cached_search(db_session, "q", client=FakeClient(res(1)), ttl_hours=1)
    assert abs(datetime.now(timezone.utc) - out.fetched_at) < timedelta(seconds=30)

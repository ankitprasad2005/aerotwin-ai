"""TTL cache of web search results in `web_search_cache`, keyed on the normalised query."""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external import WebSearchCache
from app.websearch.client import WebResult, WebSearchError

_WS_RE = re.compile(r"\s+")


class Searcher(Protocol):
    async def search(self, query: str) -> list[WebResult]: ...


@dataclass
class SearchOutcome:
    query: str  # normalised
    results: list[dict]
    cached: bool  # served from the cache (fresh or stale)
    stale: bool  # served from the cache although expired, because a refresh failed
    fetched_at: datetime


def normalise_query(query: str) -> str:
    return _WS_RE.sub(" ", query).strip().lower()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def cached_search(
    db: AsyncSession,
    query: str,
    *,
    client: Searcher,
    ttl_hours: float,
    now: datetime | None = None,
) -> SearchOutcome:
    """Return fresh cached results, else search and store them.

    An expired entry is refreshed; if the refresh fails the stale entry is served (stale=True). With no
    entry to fall back on, `WebSearchError` propagates. Writes are flushed, not committed.
    """
    key = normalise_query(query)
    moment = now or _utcnow()
    row = (await db.execute(select(WebSearchCache).where(WebSearchCache.query == key))).scalar_one_or_none()

    if row is not None and moment - row.fetched_at < timedelta(hours=ttl_hours):
        return SearchOutcome(key, list(row.results), cached=True, stale=False, fetched_at=row.fetched_at)

    try:
        results = [r.to_dict() for r in await client.search(key)]
    except WebSearchError:
        if row is None:
            raise
        return SearchOutcome(key, list(row.results), cached=True, stale=True, fetched_at=row.fetched_at)

    values = {"query": key, "results": results, "result_count": len(results), "fetched_at": moment}
    stmt = insert(WebSearchCache).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[WebSearchCache.query], set_={**values, "updated_at": moment}
    )
    await db.execute(stmt)
    await db.flush()
    return SearchOutcome(key, results, cached=False, stale=False, fetched_at=moment)

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import Settings, get_settings
from app.models.external import WebSearchCache
from app.websearch.cache import SearchOutcome, cached_search
from app.websearch.client import WebSearchError
from app.websearch.service import build_client, is_active, is_configured

router = APIRouter(prefix="/api/web-search", tags=["web-search"])

PING_TIMEOUT_SECONDS = 2.0
MAX_QUERY_CHARS = 200


class WebResultOut(BaseModel):
    title: str
    url: str
    snippet: str
    engine: str


class StatusOut(BaseModel):
    enabled: bool
    configured: bool
    reachable: bool


class SearchIn(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUERY_CHARS)]


class SearchOut(BaseModel):
    query: str
    cached: bool
    stale: bool
    fetched_at: datetime
    results: list[WebResultOut]


class CacheEntryOut(BaseModel):
    query: str
    result_count: int
    fetched_at: datetime
    results: list[WebResultOut]


async def compute_status(settings: Settings) -> StatusOut:
    reachable = False
    client = build_client(settings, timeout=min(PING_TIMEOUT_SECONDS, settings.web_search_timeout_seconds))
    if client is not None:
        reachable = await client.ping()
    return StatusOut(enabled=settings.web_search_enabled, configured=is_configured(settings), reachable=reachable)


async def run_search(db: AsyncSession, settings: Settings, query: str) -> SearchOut:
    if not is_active(settings):
        raise HTTPException(status_code=503, detail="Web search is disabled or not configured")
    client = build_client(settings)
    try:
        outcome: SearchOutcome = await cached_search(
            db, query, client=client, ttl_hours=settings.web_search_cache_ttl_hours
        )
    except WebSearchError as exc:
        raise HTTPException(status_code=502, detail=f"Web search failed: {exc}") from exc
    await db.commit()
    return SearchOut(
        query=outcome.query, cached=outcome.cached, stale=outcome.stale, fetched_at=outcome.fetched_at,
        results=outcome.results,
    )


async def list_cache(db: AsyncSession, limit: int) -> list[CacheEntryOut]:
    rows = (
        await db.execute(select(WebSearchCache).order_by(WebSearchCache.fetched_at.desc()).limit(limit))
    ).scalars().all()
    return [
        CacheEntryOut(query=r.query, result_count=r.result_count, fetched_at=r.fetched_at, results=r.results)
        for r in rows
    ]


@router.get("/status", response_model=StatusOut)
async def web_search_status(settings: Settings = Depends(get_settings)) -> StatusOut:
    return await compute_status(settings)


@router.get("/cache", response_model=list[CacheEntryOut])
async def web_search_cache(
    limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db)
) -> list[CacheEntryOut]:
    return await list_cache(db, limit)


@router.post("", response_model=SearchOut)
async def web_search_query(
    body: SearchIn, db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings)
) -> SearchOut:
    return await run_search(db, settings, body.query)

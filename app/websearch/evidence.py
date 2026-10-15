"""Web search evidence provider: one cached SearXNG query per agent, results as low-reliability evidence."""
import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.reliability import SOURCE_RELIABILITY
from app.websearch.cache import cached_search
from app.websearch.service import build_client

_ROUTE_RE = re.compile(r"[^A-Za-z0-9]+")
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_AIRCRAFT_RE = re.compile(r"\b(A3[0-9]{2}(?:neo)?|B7[0-9]{2}|737(?:-?MAX)?|ATR ?[0-9]{2}|Q400)\b", re.IGNORECASE)
_STOPWORDS = frozenset(
    "the and for with from that this into over what how which should could would can will our are "
    "all any new add more less than then also about please need want best optimise optimize improve "
    "increase decrease reduce plan analyse analyze airline flights flight route routes".split()
)
_MAX_KEYWORDS = 5
_MAX_QUERY_CHARS = 200

TEMPLATES: dict[str, str] = {
    "NETWORK": "{route} air traffic demand India {year}",
    "FLEET": "{aircraft} aircraft availability India airline {year}",
    "MAINTENANCE": "A320 maintenance check delays India {year}",
    "CREW": "India airline pilot crew shortage {year}",
    "CARGO": "{route} air cargo demand India {year}",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def objective_keywords(objective: str) -> str:
    words = [w for w in _WORD_RE.findall(objective) if len(w) >= 3 and w.lower() not in _STOPWORDS]
    return " ".join(words[:_MAX_KEYWORDS])


def build_query(request: EvidenceRequest, *, now: datetime | None = None) -> str | None:
    """The agent's search query, or None if the agent has no template."""
    template = TEMPLATES.get(request.agent_type)
    if template is None:
        return None
    year = (now or _utcnow()).year
    route = _ROUTE_RE.sub(" ", request.route or "").strip() or objective_keywords(request.objective)
    match = _AIRCRAFT_RE.search(request.objective)
    aircraft = match.group(1).upper() if match else "A320"
    query = template.format(route=route, aircraft=aircraft, year=year)
    return " ".join(query.split())[:_MAX_QUERY_CHARS]


def item_id(url: str) -> str:
    return "web:" + hashlib.sha1(url.encode()).hexdigest()[:8]


async def web_search(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    settings = get_settings()
    client = build_client(settings)
    if client is None:
        return []
    query = build_query(request)
    if query is None:
        return []
    outcome = await cached_search(db, query, client=client, ttl_hours=settings.web_search_cache_ttl_hours)
    items: list[EvidenceItem] = []
    for result in outcome.results[: settings.web_search_max_results]:
        content: dict = {"snippet": result["snippet"], "engine": result["engine"], "query": query}
        if outcome.stale:
            content["stale"] = True
        items.append(
            EvidenceItem(
                id=item_id(result["url"]),
                source="web",
                kind="web",
                title=result["title"] or result["url"],
                url=result["url"],
                fetched_at=outcome.fetched_at,
                reliability=SOURCE_RELIABILITY["web"],
                content=content,
            )
        )
    return items

"""SearXNG client. Web content is untrusted: everything is sanitised before it leaves this module."""
import asyncio
import html
import logging
import re
from dataclasses import asdict, dataclass

import httpx

logger = logging.getLogger(__name__)

TITLE_MAX = 160
SNIPPET_MAX = 300
URL_MAX = 2048
RETRIES = 2  # retries after the first attempt

_BLOCK_RE = re.compile(r"<(script|style)\b.*?(?:</\1\s*>|$)", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?(?:-->|$)", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]*(?:>|$)")
_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"^https?://[^\s/?#]+\S*$", re.IGNORECASE)


class WebSearchError(Exception):
    """The search backend failed or returned something unusable."""


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    snippet: str
    engine: str

    def to_dict(self) -> dict:
        return asdict(self)


def sanitise_text(value: object, limit: int) -> str:
    """Strip HTML (tags, scripts, styles, comments), unescape entities, collapse whitespace, truncate."""
    if not isinstance(value, str):
        return ""
    text = _BLOCK_RE.sub(" ", value)
    text = _COMMENT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()[:limit].strip()


def sanitise_url(value: object) -> str | None:
    """Return the URL if it is a plain http(s) URL, else None."""
    if not isinstance(value, str):
        return None
    url = value.strip()
    if len(url) > URL_MAX or not _URL_RE.match(url):
        return None
    return url


def parse_results(payload: object, max_results: int) -> list[WebResult]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise WebSearchError("unexpected response shape from SearXNG")
    results: list[WebResult] = []
    seen: set[str] = set()
    for entry in payload["results"]:
        if len(results) >= max_results:
            break
        if not isinstance(entry, dict):
            continue
        url = sanitise_url(entry.get("url"))
        if url is None or url in seen:
            continue
        seen.add(url)
        results.append(
            WebResult(
                title=sanitise_text(entry.get("title"), TITLE_MAX),
                url=url,
                snippet=sanitise_text(entry.get("content"), SNIPPET_MAX),
                engine=sanitise_text(entry.get("engine"), 40),
            )
        )
    return results


class SearxngClient:
    def __init__(self, base_url: str, *, timeout: float, max_results: int, backoff: float = 0.3):
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._max_results = max_results
        self._backoff = backoff

    async def search(self, query: str) -> list[WebResult]:
        params = {"q": query, "format": "json", "language": "en", "safesearch": "1"}
        last = "unknown error"
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            for attempt in range(RETRIES + 1):
                if attempt:
                    await asyncio.sleep(self._backoff * attempt)
                try:
                    response = await http.get(f"{self._base}/search", params=params)
                except httpx.HTTPError as exc:
                    last = type(exc).__name__
                    logger.warning("searxng request failed (attempt %d): %s", attempt + 1, last)
                    continue
                if response.status_code >= 500:
                    last = f"HTTP {response.status_code}"
                    logger.warning("searxng returned %s (attempt %d)", last, attempt + 1)
                    continue
                if response.status_code >= 400:
                    raise WebSearchError(f"SearXNG returned HTTP {response.status_code}")
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise WebSearchError("SearXNG returned invalid JSON") from exc
                return parse_results(payload, self._max_results)
        raise WebSearchError(f"SearXNG unavailable after {RETRIES + 1} attempts: {last}")

    async def ping(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                response = await http.get(f"{self._base}/healthz")
        except httpx.HTTPError:
            return False
        return response.is_success

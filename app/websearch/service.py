"""Wiring shared by the evidence provider and the API: settings -> client."""
from app.config import Settings
from app.websearch.client import SearxngClient


def is_configured(settings: Settings) -> bool:
    return bool(settings.searxng_url and settings.searxng_url.strip())


def is_active(settings: Settings) -> bool:
    return settings.web_search_enabled and is_configured(settings)


def build_client(settings: Settings, *, timeout: float | None = None) -> SearxngClient | None:
    """A client for the configured SearXNG, or None when web search is disabled or unconfigured."""
    if not is_active(settings):
        return None
    return SearxngClient(
        settings.searxng_url.strip(),
        timeout=timeout if timeout is not None else settings.web_search_timeout_seconds,
        max_results=settings.web_search_max_results,
    )

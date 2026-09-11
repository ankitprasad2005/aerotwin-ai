from app.api.deps import get_bus, get_llm_provider
from app.config import get_settings
from app.events.bus import event_bus
from app.llm.openai_provider import OpenAIProvider


def test_get_bus_returns_the_module_singleton():
    """The get_bus dependency must resolve to the process-wide EventBus instance,
    not a fresh one, so all websocket subscribers and event publishers share it."""
    assert get_bus() is event_bus


def test_get_llm_provider_returns_an_openai_provider_instance(monkeypatch):
    """The get_llm_provider dependency is the production wiring for the /runs
    endpoint's real (non-test) LLM calls: it must construct a real OpenAIProvider."""
    monkeypatch.setenv("AEROTWIN_OPENAI_API_KEY", "sk-test-key")
    get_settings.cache_clear()
    try:
        provider = get_llm_provider()
        assert isinstance(provider, OpenAIProvider)
    finally:
        get_settings.cache_clear()

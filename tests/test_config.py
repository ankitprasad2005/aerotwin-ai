import os

from app.config import Settings


def test_settings_default_model_is_gpt4o_mini(monkeypatch):
    monkeypatch.delenv("AEROTWIN_OPENAI_MODEL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_model == "gpt-4o-mini"


def test_settings_reads_env_override(monkeypatch):
    monkeypatch.setenv("AEROTWIN_OPENAI_MODEL", "gpt-4.1")
    settings = Settings(_env_file=None)
    assert settings.openai_model == "gpt-4.1"


def test_get_settings_is_cached():
    from app.config import get_settings

    assert get_settings() is get_settings()


def test_settings_default_database_url(monkeypatch):
    monkeypatch.delenv("AEROTWIN_DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+asyncpg://aerotwin:aerotwin@postgres:5432/aerotwin"


def test_settings_default_openai_api_key_is_empty(monkeypatch):
    monkeypatch.delenv("AEROTWIN_OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_api_key == ""


def test_settings_default_openai_base_url_is_none(monkeypatch):
    monkeypatch.delenv("AEROTWIN_OPENAI_BASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_base_url is None


def test_settings_blank_openai_base_url_env_is_treated_as_unset(monkeypatch):
    """.env.example ships `AEROTWIN_OPENAI_BASE_URL=` (blank) — that must mean "use the
    OpenAI default", not an empty base URL that breaks every request."""
    monkeypatch.setenv("AEROTWIN_OPENAI_BASE_URL", "")
    settings = Settings(_env_file=None)
    assert settings.openai_base_url is None


def test_settings_openai_base_url_env_override(monkeypatch):
    monkeypatch.setenv("AEROTWIN_OPENAI_BASE_URL", "https://llm-proxy.example.com/v1")
    settings = Settings(_env_file=None)
    assert settings.openai_base_url == "https://llm-proxy.example.com/v1"


def test_settings_cors_origins_env_override(monkeypatch):
    monkeypatch.setenv("AEROTWIN_CORS_ORIGINS", '["https://example.com"]')
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["https://example.com"]


import pytest
from pydantic import ValidationError


def test_settings_default_agent_concurrency_is_4(monkeypatch):
    monkeypatch.delenv("AEROTWIN_AGENT_CONCURRENCY", raising=False)
    assert Settings(_env_file=None).agent_concurrency == 4


def test_settings_reads_agent_concurrency_override(monkeypatch):
    monkeypatch.setenv("AEROTWIN_AGENT_CONCURRENCY", "2")
    assert Settings(_env_file=None).agent_concurrency == 2


@pytest.mark.parametrize("value", ["0", "-1"])
def test_settings_rejects_agent_concurrency_below_one(monkeypatch, value):
    monkeypatch.setenv("AEROTWIN_AGENT_CONCURRENCY", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_rejects_non_integer_agent_concurrency(monkeypatch):
    monkeypatch.setenv("AEROTWIN_AGENT_CONCURRENCY", "many")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# --- evidence / web search settings ---------------------------------------------------------------

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402


def test_evidence_settings_defaults(monkeypatch):
    for name in (
        "SEARXNG_URL", "WEB_SEARCH_ENABLED", "WEB_SEARCH_TIMEOUT_SECONDS", "WEB_SEARCH_CACHE_TTL_HOURS",
        "WEB_SEARCH_MAX_RESULTS", "DATASETS_DIR", "EVIDENCE_MAX_ITEMS_PER_AGENT",
        "EVIDENCE_MAX_CHARS_PER_AGENT", "EVIDENCE_PROVIDER_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(f"AEROTWIN_{name}", raising=False)
    settings = Settings(_env_file=None)
    assert settings.searxng_url is None
    assert settings.web_search_enabled is True
    assert settings.web_search_timeout_seconds == 8.0
    assert settings.web_search_cache_ttl_hours == 24.0
    assert settings.web_search_max_results == 5
    assert settings.datasets_dir == "data/datasets"
    assert settings.evidence_max_items_per_agent == 8
    assert settings.evidence_max_chars_per_agent == 6000
    assert settings.evidence_provider_timeout_seconds == 15.0


def test_evidence_settings_env_overrides(monkeypatch):
    monkeypatch.setenv("AEROTWIN_SEARXNG_URL", "http://searxng:8080")
    monkeypatch.setenv("AEROTWIN_WEB_SEARCH_ENABLED", "false")
    monkeypatch.setenv("AEROTWIN_WEB_SEARCH_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("AEROTWIN_WEB_SEARCH_CACHE_TTL_HOURS", "1")
    monkeypatch.setenv("AEROTWIN_WEB_SEARCH_MAX_RESULTS", "10")
    monkeypatch.setenv("AEROTWIN_DATASETS_DIR", "/tmp/ds")
    monkeypatch.setenv("AEROTWIN_EVIDENCE_MAX_ITEMS_PER_AGENT", "0")
    monkeypatch.setenv("AEROTWIN_EVIDENCE_MAX_CHARS_PER_AGENT", "500")
    monkeypatch.setenv("AEROTWIN_EVIDENCE_PROVIDER_TIMEOUT_SECONDS", "0.5")
    settings = Settings(_env_file=None)
    assert settings.searxng_url == "http://searxng:8080"
    assert settings.web_search_enabled is False
    assert settings.web_search_timeout_seconds == 2.5
    assert settings.web_search_cache_ttl_hours == 1.0
    assert settings.web_search_max_results == 10
    assert settings.datasets_dir == "/tmp/ds"
    assert settings.evidence_max_items_per_agent == 0
    assert settings.evidence_max_chars_per_agent == 500
    assert settings.evidence_provider_timeout_seconds == 0.5


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_searxng_url_is_treated_as_unset(monkeypatch, blank):
    monkeypatch.setenv("AEROTWIN_SEARXNG_URL", blank)
    assert Settings(_env_file=None).searxng_url is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("WEB_SEARCH_CACHE_TTL_HOURS", "0"),
        ("WEB_SEARCH_CACHE_TTL_HOURS", "-1"),
        ("WEB_SEARCH_MAX_RESULTS", "0"),
        ("WEB_SEARCH_MAX_RESULTS", "11"),
        ("EVIDENCE_MAX_ITEMS_PER_AGENT", "-1"),
        ("EVIDENCE_MAX_CHARS_PER_AGENT", "499"),
        ("EVIDENCE_PROVIDER_TIMEOUT_SECONDS", "0"),
        ("EVIDENCE_PROVIDER_TIMEOUT_SECONDS", "-3"),
    ],
)
def test_out_of_bounds_evidence_settings_are_rejected(monkeypatch, name, value):
    monkeypatch.setenv(f"AEROTWIN_{name}", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_ignores_unrelated_keys_in_the_shared_env_file(tmp_path):
    # .env also carries docker-compose-only keys such as SEARXNG_SECRET (see .env.example).
    env_file = tmp_path / ".env"
    env_file.write_text("SEARXNG_SECRET=abc\nAEROTWIN_OPENAI_MODEL=from-file\n")
    settings = Settings(_env_file=env_file)
    assert settings.openai_model == "from-file"

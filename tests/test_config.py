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

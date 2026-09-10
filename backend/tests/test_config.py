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

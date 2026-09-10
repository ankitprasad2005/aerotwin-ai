from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration; fields are overridable via env vars prefixed with AEROTWIN_."""

    database_url: str = "postgresql+asyncpg://aerotwin:aerotwin@postgres:5432/aerotwin"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    openai_timeout_seconds: float = 30.0
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AEROTWIN_")


@lru_cache
def get_settings() -> Settings:
    """Cached DI entrypoint for obtaining the process-wide Settings instance."""
    return Settings()

from functools import lru_cache

from pydantic import field_validator
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

    @field_validator("openai_base_url", mode="before")
    @classmethod
    def _blank_base_url_means_default(cls, value: object) -> object:
        # .env.example ships `AEROTWIN_OPENAI_BASE_URL=` (blank). Passed through as "",
        # AsyncOpenAI treats it as an explicit base URL (not "use the default"), so
        # every request would fail — normalize blank to None instead.
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    """Cached DI entrypoint for obtaining the process-wide Settings instance."""
    return Settings()

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
    # Origins allowed in addition to cors_origins. Defaults to any loopback or private-LAN
    # address on any port, so the UI works when opened from another device or container on the
    # same network (where the browser's origin is the host's LAN IP, not localhost). Set to an
    # empty value to allow only cors_origins.
    cors_origin_regex: str | None = (
        r"^https?://(localhost|127\.0\.0\.1|\[::1\]|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?$"
    )

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AEROTWIN_")

    @field_validator("openai_base_url", "cors_origin_regex", mode="before")
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        # A blank env var means "not configured", not "an empty value". e.g. .env.example ships
        # `AEROTWIN_OPENAI_BASE_URL=`; passed through as "", AsyncOpenAI would treat it as an
        # explicit base URL and every request would fail. An empty CORS regex matches nothing.
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    """Cached DI entrypoint for obtaining the process-wide Settings instance."""
    return Settings()

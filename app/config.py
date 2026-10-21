from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration; fields are overridable via env vars prefixed with AEROTWIN_."""

    database_url: str = "postgresql+asyncpg://aerotwin:aerotwin@postgres:5432/aerotwin"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    openai_timeout_seconds: float = 60.0
    # Extra attempts after a timeout, connection error, rate limit or 5xx (never after a 4xx or a schema error).
    openai_max_retries: int = Field(default=2, ge=0)
    # Extra attempts when a reply is cut off by the length limit or fails the output schema. Off for hosted
    # models (a bad reply would mostly repeat); local mode turns it on, since a small model only sometimes
    # samples a bad reply and another draw usually fits.
    openai_invalid_output_retries: int = Field(default=0, ge=0)
    # Upper bound on agents running at once within an iteration (limits parallel LLM calls).
    agent_concurrency: int = Field(default=4, ge=1)
    # On-device inference: when true, agents talk to a local llama.cpp server (OpenAI-compatible) instead
    # of openai_base_url/openai_model. See _apply_local_llm for the overrides it implies.
    local_llm: bool = False
    # docker-compose sets http://llm:8080/v1 (the llm service).
    local_llm_base_url: str = "http://localhost:8080/v1"
    # Must match the llama.cpp server's --alias.
    local_llm_model: str = "local"
    # Self-hosted SearXNG for web evidence; None disables web search (blank env var -> None).
    searxng_url: str | None = None
    web_search_enabled: bool = True
    web_search_timeout_seconds: float = 8.0
    web_search_cache_ttl_hours: float = Field(default=24.0, gt=0)
    web_search_max_results: int = Field(default=5, ge=1, le=10)
    # OpenSky Network OAuth2 client (https://opensky-network.org); blank = anonymous access, which cannot read
    # arrivals/departures. See app/datasets/opensky_live.py.
    opensky_client_id: str = ""
    opensky_client_secret: str = ""
    # Where downloaded datasets (OpenFlights, EIA, DGCA) are stored; never committed.
    datasets_dir: str = "data/datasets"
    # Caps on the external evidence put into each agent's context (bounds LLM token use).
    evidence_max_items_per_agent: int = Field(default=14, ge=0)
    evidence_max_chars_per_agent: int = Field(default=10000, ge=500)
    evidence_provider_timeout_seconds: float = Field(default=15.0, gt=0)
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

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AEROTWIN_", extra="ignore")

    @field_validator("openai_base_url", "cors_origin_regex", "searxng_url", mode="before")
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        # A blank env var means "not configured", not "an empty value". e.g. .env.example ships
        # `AEROTWIN_OPENAI_BASE_URL=`; passed through as "", AsyncOpenAI would treat it as an
        # explicit base URL and every request would fail. An empty CORS regex matches nothing.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _apply_local_llm(self) -> "Settings":
        # Plain assignment is safe here: validate_assignment is off, so this does not re-run validation.
        if not self.local_llm:
            return self
        self.openai_base_url = self.local_llm_base_url
        self.openai_model = self.local_llm_model
        # AsyncOpenAI refuses an empty key; llama.cpp ignores whatever is sent.
        self.openai_api_key = self.openai_api_key or "local-not-used"
        # CPU inference takes minutes per agent, and one agent at a time keeps a small board from
        # swapping. Explicitly configured values always win.
        if "openai_timeout_seconds" not in self.model_fields_set:
            self.openai_timeout_seconds = 1800.0
        if "agent_concurrency" not in self.model_fields_set:
            self.agent_concurrency = 1
        if "openai_invalid_output_retries" not in self.model_fields_set:
            self.openai_invalid_output_retries = 2
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached DI entrypoint for obtaining the process-wide Settings instance."""
    return Settings()

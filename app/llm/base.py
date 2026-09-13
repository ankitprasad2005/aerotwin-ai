from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResponse(Generic[T]):
    """Result of one LLMProvider.complete() call, with parsed already validated against output_schema."""

    provider: str
    model: str
    request_id: str
    raw_response: dict
    parsed: T
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float | None
    duration_ms: int
    retry_count: int


class LLMProviderError(Exception):
    """Raised for any LLM call failure: transport errors, timeouts, or output that fails schema validation."""


@runtime_checkable
class LLMProvider(Protocol):
    """Structural interface every LLM backend (fake, OpenAI, ...) implements — agents depend only on this."""

    async def complete(
        self,
        *,
        system_instructions: str,
        context: dict,
        task: str,
        available_tools: list[str],
        output_schema: type[T],
    ) -> LLMResponse[T]: ...

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass
class LLMResponse:
    provider: str
    model: str
    request_id: str
    raw_response: dict
    parsed: BaseModel
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float | None
    duration_ms: int
    retry_count: int


class LLMProviderError(Exception):
    pass


class LLMProvider(Protocol):
    async def complete(
        self,
        *,
        system_instructions: str,
        context: dict,
        task: str,
        available_tools: list[str],
        output_schema: type[BaseModel],
    ) -> LLMResponse: ...

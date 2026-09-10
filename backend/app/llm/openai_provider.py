import time

from openai import AsyncOpenAI

from app.config import get_settings
from app.llm.base import LLMProviderError, LLMResponse, T


class OpenAIProvider:
    """Real LLMProvider backed by the OpenAI SDK's structured-output (beta) API."""

    def __init__(self, client: AsyncOpenAI | None = None, model: str | None = None):
        settings = get_settings()
        self._client = client or AsyncOpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url
        )
        self._model = model or settings.openai_model

    async def complete(
        self,
        *,
        system_instructions: str,
        context: dict,
        task: str,
        available_tools: list[str],
        output_schema: type[T],
    ) -> LLMResponse[T]:
        started = time.monotonic()
        try:
            completion = await self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_instructions},
                    {
                        "role": "user",
                        "content": (
                            f"Context:\n{context}\n\nTask:\n{task}\n\n"
                            f"Available tools: {available_tools}"
                        ),
                    },
                ],
                response_format=output_schema,
            )
        except Exception as exc:
            raise LLMProviderError(f"OpenAI request failed: {exc}") from exc

        duration_ms = int((time.monotonic() - started) * 1000)
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise LLMProviderError("OpenAI response failed structured-output parsing")

        usage = completion.usage
        return LLMResponse(
            provider="openai",
            model=completion.model,
            request_id=completion.id,
            raw_response=completion.model_dump(),
            parsed=parsed,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            estimated_cost=None,
            duration_ms=duration_ms,
            retry_count=0,
        )

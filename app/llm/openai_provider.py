import json
import time

import openai
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config import get_settings
from app.llm.base import LLMProviderError, LLMResponse, T


class OpenAIProvider:
    """Real LLMProvider backed by the OpenAI SDK's structured-output (beta) API.

    Makes no retries itself (max_retries=0) — retry_count is always 0 by design;
    retry policy is left to the caller.
    """

    def __init__(self, client: AsyncOpenAI | None = None, model: str | None = None):
        settings = get_settings()
        # Client construction is deliberately deferred to complete() (not done here),
        # so that a missing/invalid API key surfaces as a normal LLMProviderError ->
        # AgentRunError -> FAILED run with full observability, instead of crashing
        # get_llm_provider()'s FastAPI dependency injection with an unhandled 500
        # before the orchestration pipeline's own error handling ever runs.
        self._client = client
        self._settings = settings
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
            if self._client is None:
                self._client = AsyncOpenAI(
                    api_key=self._settings.openai_api_key,
                    base_url=self._settings.openai_base_url,
                    max_retries=0,
                    timeout=self._settings.openai_timeout_seconds,
                )
            completion = await self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_instructions},
                    {
                        "role": "user",
                        "content": (
                            f"Context:\n{json.dumps(context, indent=2, default=str)}\n\n"
                            f"Task:\n{task}\n\n"
                            f"Available tools: {json.dumps(available_tools)}"
                        ),
                    },
                ],
                response_format=output_schema,
            )
        except openai.OpenAIError as exc:
            raise LLMProviderError(f"OpenAI request failed: {exc}") from exc
        except ValidationError as exc:
            # parse() validates the model's JSON against output_schema client-side and
            # raises pydantic's ValidationError (not an OpenAIError) when it doesn't fit.
            raise LLMProviderError(f"OpenAI output failed schema validation: {exc}") from exc

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
            # TODO: compute from model+token pricing once a rate table exists
            estimated_cost=None,
            duration_ms=duration_ms,
            retry_count=0,
        )

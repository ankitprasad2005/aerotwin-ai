import asyncio
import json
import time

import openai
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config import get_settings
from app.llm.base import LLMProviderError, LLMResponse, T

# Transient failures worth another attempt; a 4xx or a schema error would fail the same way again.
RETRYABLE_ERRORS = (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError)
RETRY_BACKOFF_SECONDS = 1.0  # multiplied by the attempt number


class OpenAIProvider:
    """Real LLMProvider backed by the OpenAI SDK's structured-output (beta) API.

    The SDK's own retries are off (max_retries=0); this class retries transient failures itself, up to
    settings.openai_max_retries extra attempts with a linear backoff, so retry_count records what happened.
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
        attempts = 1 + self._settings.openai_max_retries
        for attempt in range(1, attempts + 1):
            try:
                completion = await self._request(system_instructions, context, task, available_tools, output_schema)
                break
            except RETRYABLE_ERRORS as exc:
                if attempt == attempts:
                    raise LLMProviderError(f"OpenAI request failed after {attempts} attempts: {exc}") from exc
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

        duration_ms = int((time.monotonic() - started) * 1000)
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise LLMProviderError("OpenAI response failed structured-output parsing")

        usage = completion.usage
        return LLMResponse(
            provider="openai",
            model=completion.model,
            request_id=completion.id,
            # warnings=False: ParsedChatCompletion's generic `parsed` field makes pydantic emit a
            # PydanticSerializationUnexpectedValue UserWarning on every call otherwise (log spam only;
            # the dumped dict is correct).
            raw_response=completion.model_dump(warnings=False),
            parsed=parsed,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            # TODO: compute from model+token pricing once a rate table exists
            estimated_cost=None,
            duration_ms=duration_ms,
            retry_count=attempt - 1,
        )

    async def _request(self, system_instructions, context, task, available_tools, output_schema):
        """One structured-output call; transient SDK errors propagate for complete() to retry."""
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
        except RETRYABLE_ERRORS:
            raise
        except openai.OpenAIError as exc:
            raise LLMProviderError(f"OpenAI request failed: {exc}") from exc
        except ValidationError as exc:
            # parse() validates the model's JSON against output_schema client-side and
            # raises pydantic's ValidationError (not an OpenAIError) when it doesn't fit.
            raise LLMProviderError(f"OpenAI output failed schema validation: {exc}") from exc
        return completion

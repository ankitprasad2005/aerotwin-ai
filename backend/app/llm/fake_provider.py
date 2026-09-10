import uuid

from pydantic import BaseModel, ValidationError

from app.llm.base import LLMProviderError, LLMResponse


class FakeLLMProvider:
    def __init__(self, canned_response: dict | None = None, should_fail: bool = False):
        self.canned_response = canned_response or {}
        self.should_fail = should_fail
        self.calls: list[dict] = []

    async def complete(
        self,
        *,
        system_instructions: str,
        context: dict,
        task: str,
        available_tools: list[str],
        output_schema: type[BaseModel],
    ) -> LLMResponse:
        self.calls.append({"system_instructions": system_instructions, "context": context, "task": task})

        if self.should_fail:
            raise LLMProviderError("fake provider forced failure")

        try:
            parsed = output_schema.model_validate(self.canned_response)
        except ValidationError as exc:
            raise LLMProviderError(f"fake provider output failed schema validation: {exc}") from exc

        return LLMResponse(
            provider="fake",
            model="fake-model",
            request_id=str(uuid.uuid4()),
            raw_response={"canned_response": self.canned_response},
            parsed=parsed,
            input_tokens=120,
            output_tokens=60,
            total_tokens=180,
            estimated_cost=0.0,
            duration_ms=5,
            retry_count=0,
        )

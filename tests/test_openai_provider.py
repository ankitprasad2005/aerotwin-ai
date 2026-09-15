import httpx
import openai
import pytest
from pydantic import BaseModel

from app.llm.base import LLMProviderError
from app.llm.openai_provider import OpenAIProvider


class _Recommendation(BaseModel):
    route: str
    confidence: float


class _StubMessage:
    def __init__(self, parsed):
        self.parsed = parsed


class _StubChoice:
    def __init__(self, parsed):
        self.message = _StubMessage(parsed)


class _StubUsage:
    prompt_tokens = 200
    completion_tokens = 80
    total_tokens = 280


class _StubCompletion:
    def __init__(self, parsed):
        self.id = "chatcmpl-test-1"
        self.model = "gpt-4o-mini"
        self.choices = [_StubChoice(parsed)]
        self.usage = _StubUsage()

    def model_dump(self):
        return {"id": self.id, "model": self.model}


class _StubParseSuccess:
    async def parse(self, **kwargs):
        return _StubCompletion(_Recommendation(route="BOM-DEL", confidence=0.8))


class _StubParseReturnsNone:
    async def parse(self, **kwargs):
        return _StubCompletion(None)


class _StubParseRaises:
    async def parse(self, **kwargs):
        raise openai.APIConnectionError(
            message="network exploded",
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        )


def _client_with(completions_stub):
    class _Completions:
        parse = completions_stub.parse

    class _Chat:
        completions = _Completions()

    class _Beta:
        chat = _Chat()

    class _Client:
        beta = _Beta()

    return _Client()


async def test_openai_provider_returns_parsed_recommendation():
    provider = OpenAIProvider(client=_client_with(_StubParseSuccess()), model="gpt-4o-mini")

    response = await provider.complete(
        system_instructions="sys", context={"a": 1}, task="t",
        available_tools=["query_route_profitability"], output_schema=_Recommendation,
    )

    assert response.provider == "openai"
    assert response.parsed.route == "BOM-DEL"
    assert response.input_tokens == 200
    assert response.total_tokens == 280


async def test_openai_provider_raises_on_transport_error():
    provider = OpenAIProvider(client=_client_with(_StubParseRaises()), model="gpt-4o-mini")

    with pytest.raises(LLMProviderError):
        await provider.complete(
            system_instructions="sys", context={}, task="t",
            available_tools=[], output_schema=_Recommendation,
        )


async def test_openai_provider_raises_when_structured_parse_fails():
    provider = OpenAIProvider(client=_client_with(_StubParseReturnsNone()), model="gpt-4o-mini")

    with pytest.raises(LLMProviderError):
        await provider.complete(
            system_instructions="sys", context={}, task="t",
            available_tools=[], output_schema=_Recommendation,
        )


def test_openai_provider_defers_client_construction_until_first_complete_call(monkeypatch):
    monkeypatch.setenv("AEROTWIN_OPENAI_API_KEY", "sk-test-key")
    from app.config import get_settings
    get_settings.cache_clear()

    provider = OpenAIProvider(model="gpt-4o-mini")

    # Client is NOT constructed at __init__ time — deferred to complete(), so that
    # a missing/invalid key surfaces as a normal LLMProviderError (caught by the
    # agent runner) instead of crashing FastAPI's dependency injection with an
    # unhandled 500 before the orchestration pipeline's own error handling runs.
    assert provider._client is None
    assert provider._model == "gpt-4o-mini"
    get_settings.cache_clear()


async def test_openai_provider_missing_api_key_raises_llm_provider_error_not_crash(monkeypatch):
    monkeypatch.setenv("AEROTWIN_OPENAI_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()

    provider = OpenAIProvider(model="gpt-4o-mini")

    with pytest.raises(LLMProviderError):
        await provider.complete(
            system_instructions="sys", context={}, task="t",
            available_tools=[], output_schema=_Recommendation,
        )

    get_settings.cache_clear()


async def test_openai_provider_caches_lazily_constructed_client_across_calls():
    provider = OpenAIProvider(client=_client_with(_StubParseSuccess()), model="gpt-4o-mini")

    await provider.complete(
        system_instructions="sys", context={}, task="t",
        available_tools=[], output_schema=_Recommendation,
    )
    first_client = provider._client

    await provider.complete(
        system_instructions="sys", context={}, task="t",
        available_tools=[], output_schema=_Recommendation,
    )

    assert provider._client is first_client


def test_openai_provider_uses_default_model_from_settings(monkeypatch):
    monkeypatch.setenv("AEROTWIN_OPENAI_MODEL", "gpt-4.1")
    from app.config import get_settings
    get_settings.cache_clear()

    provider = OpenAIProvider(client=_client_with(_StubParseSuccess()))

    assert provider._model == "gpt-4.1"
    get_settings.cache_clear()


async def test_openai_provider_handles_missing_usage():
    class _StubCompletionNoUsage(_StubCompletion):
        def __init__(self, parsed):
            super().__init__(parsed)
            self.usage = None

    class _StubParseNoUsage:
        async def parse(self, **kwargs):
            return _StubCompletionNoUsage(_Recommendation(route="BOM-DEL", confidence=0.8))

    provider = OpenAIProvider(client=_client_with(_StubParseNoUsage()), model="gpt-4o-mini")

    response = await provider.complete(
        system_instructions="sys", context={}, task="t",
        available_tools=[], output_schema=_Recommendation,
    )

    assert response.input_tokens == 0
    assert response.output_tokens == 0
    assert response.total_tokens == 0


async def test_openai_provider_wraps_client_side_schema_validation_error():
    """parse() raises pydantic's ValidationError (not an OpenAIError) when the model's
    JSON doesn't fit output_schema; the LLMProvider contract says that's an LLMProviderError."""
    try:
        _Recommendation.model_validate({"route": "BOM-DEL", "confidence": "not-a-number"})
    except Exception as exc:  # noqa: BLE001 — capturing the real ValidationError instance
        validation_error = exc

    class _StubParseInvalidOutput:
        async def parse(self, **kwargs):
            raise validation_error

    provider = OpenAIProvider(client=_client_with(_StubParseInvalidOutput()), model="gpt-4o-mini")

    with pytest.raises(LLMProviderError):
        await provider.complete(
            system_instructions="sys", context={}, task="t",
            available_tools=[], output_schema=_Recommendation,
        )


async def test_openai_provider_lets_non_openai_errors_propagate():
    class _StubParseTypeError:
        async def parse(self, **kwargs):
            raise TypeError("programmer error, not an API failure")

    provider = OpenAIProvider(client=_client_with(_StubParseTypeError()), model="gpt-4o-mini")

    with pytest.raises(TypeError):
        await provider.complete(
            system_instructions="sys", context={}, task="t",
            available_tools=[], output_schema=_Recommendation,
        )


async def test_openai_provider_serializes_context_as_json():
    captured_kwargs = {}

    class _StubParseCapture:
        async def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return _StubCompletion(_Recommendation(route="BOM-DEL", confidence=0.8))

    provider = OpenAIProvider(client=_client_with(_StubParseCapture()), model="gpt-4o-mini")

    await provider.complete(
        system_instructions="sys", context={"route": "BOM-DEL", "demand": 18000}, task="t",
        available_tools=["query_route_profitability"], output_schema=_Recommendation,
    )

    user_message = captured_kwargs["messages"][1]["content"]
    assert '"route": "BOM-DEL"' in user_message
    assert '"demand": 18000' in user_message

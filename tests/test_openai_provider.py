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

    def model_dump(self, **kwargs):
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


@pytest.fixture(autouse=True)
def _no_retry_backoff(monkeypatch):
    monkeypatch.setattr("app.llm.openai_provider.RETRY_BACKOFF_SECONDS", 0)


_REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


class _StubFlaky:
    """Fails with the given errors in order, then succeeds."""

    def __init__(self, *errors):
        self.errors = list(errors)
        self.calls = 0

    async def parse(self, **kwargs):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return _StubCompletion(_Recommendation(route="BOM-DEL", confidence=0.8))


async def _complete(provider):
    return await provider.complete(
        system_instructions="sys", context={}, task="t", available_tools=[], output_schema=_Recommendation,
    )


async def test_a_timeout_is_retried_and_the_retry_is_recorded():
    stub = _StubFlaky(openai.APITimeoutError(request=_REQUEST))
    response = await _complete(OpenAIProvider(client=_client_with(stub), model="m"))
    assert response.parsed.route == "BOM-DEL"
    assert stub.calls == 2 and response.retry_count == 1


async def test_retries_stop_after_the_configured_limit(monkeypatch):
    monkeypatch.setenv("AEROTWIN_OPENAI_MAX_RETRIES", "2")
    from app.config import get_settings
    get_settings.cache_clear()
    stub = _StubFlaky(*[openai.APIConnectionError(message="down", request=_REQUEST) for _ in range(5)])
    with pytest.raises(LLMProviderError, match="after 3 attempts"):
        await _complete(OpenAIProvider(client=_client_with(stub), model="m"))
    assert stub.calls == 3
    get_settings.cache_clear()


async def test_a_client_error_is_not_retried():
    error = openai.BadRequestError(message="bad", response=httpx.Response(400, request=_REQUEST), body=None)
    stub = _StubFlaky(error)
    with pytest.raises(LLMProviderError):
        await _complete(OpenAIProvider(client=_client_with(stub), model="m"))
    assert stub.calls == 1


# --- invalid structured output (cut off by the length limit, or outside the schema) -----------------


def _schema_validation_error():
    try:
        _Recommendation.model_validate({"route": "BOM-DEL", "confidence": "not-a-number"})
    except Exception as exc:  # noqa: BLE001 — capturing the real ValidationError instance
        return exc


def _length_limit_error():
    return openai.LengthFinishReasonError(completion=_StubCompletion(None))


@pytest.fixture
def invalid_output_retries(monkeypatch):
    from app.config import get_settings

    def _set(value):
        monkeypatch.setenv("AEROTWIN_OPENAI_INVALID_OUTPUT_RETRIES", str(value))
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


async def test_an_invalid_output_is_not_retried_by_default():
    stub = _StubFlaky(_schema_validation_error())
    with pytest.raises(LLMProviderError, match="schema validation"):
        await _complete(OpenAIProvider(client=_client_with(stub), model="m"))
    assert stub.calls == 1


async def test_a_schema_invalid_output_is_retried_when_configured(invalid_output_retries):
    invalid_output_retries(2)
    stub = _StubFlaky(_schema_validation_error())
    response = await _complete(OpenAIProvider(client=_client_with(stub), model="m"))
    assert response.parsed.route == "BOM-DEL"
    assert stub.calls == 2 and response.retry_count == 1


async def test_a_reply_cut_off_by_the_length_limit_is_retried_when_configured(invalid_output_retries):
    invalid_output_retries(1)
    stub = _StubFlaky(_length_limit_error())
    response = await _complete(OpenAIProvider(client=_client_with(stub), model="m"))
    assert stub.calls == 2 and response.retry_count == 1


async def test_invalid_output_retries_stop_after_the_configured_limit(invalid_output_retries):
    invalid_output_retries(2)
    stub = _StubFlaky(*[_length_limit_error() for _ in range(5)])
    with pytest.raises(LLMProviderError, match="after 3 attempts"):
        await _complete(OpenAIProvider(client=_client_with(stub), model="m"))
    assert stub.calls == 3


async def test_a_client_error_is_still_not_retried_with_invalid_output_retries_on(invalid_output_retries):
    invalid_output_retries(2)
    error = openai.BadRequestError(message="bad", response=httpx.Response(400, request=_REQUEST), body=None)
    stub = _StubFlaky(error)
    with pytest.raises(LLMProviderError):
        await _complete(OpenAIProvider(client=_client_with(stub), model="m"))
    assert stub.calls == 1

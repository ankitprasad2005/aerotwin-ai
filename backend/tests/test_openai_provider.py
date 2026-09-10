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
        raise RuntimeError("network exploded")


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

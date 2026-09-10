import pytest
from pydantic import BaseModel

from app.llm.base import LLMProviderError
from app.llm.fake_provider import FakeLLMProvider


class _Recommendation(BaseModel):
    route: str
    confidence: float


async def test_fake_provider_returns_validated_parsed_output():
    provider = FakeLLMProvider(canned_response={"route": "BOM-DEL", "confidence": 0.8})

    response = await provider.complete(
        system_instructions="sys", context={"a": 1}, task="do it",
        available_tools=["query_route_profitability"], output_schema=_Recommendation,
    )

    assert isinstance(response.parsed, _Recommendation)
    assert response.parsed.route == "BOM-DEL"
    assert response.total_tokens == response.input_tokens + response.output_tokens
    assert len(provider.calls) == 1


async def test_fake_provider_forced_failure_raises_llm_provider_error():
    provider = FakeLLMProvider(should_fail=True)

    with pytest.raises(LLMProviderError):
        await provider.complete(
            system_instructions="sys", context={}, task="t",
            available_tools=[], output_schema=_Recommendation,
        )


async def test_fake_provider_malformed_output_raises_llm_provider_error():
    provider = FakeLLMProvider(canned_response={"route": "BOM-DEL"})  # missing required "confidence"

    with pytest.raises(LLMProviderError):
        await provider.complete(
            system_instructions="sys", context={}, task="t",
            available_tools=[], output_schema=_Recommendation,
        )


async def test_fake_provider_records_all_call_parameters():
    provider = FakeLLMProvider(canned_response={"route": "BOM-DEL", "confidence": 0.8})

    await provider.complete(
        system_instructions="sys", context={"a": 1}, task="do it",
        available_tools=["query_route_profitability"], output_schema=_Recommendation,
    )

    assert provider.calls[0]["available_tools"] == ["query_route_profitability"]
    assert provider.calls[0]["output_schema"] is _Recommendation


async def test_fake_provider_accumulates_calls_across_multiple_invocations():
    provider = FakeLLMProvider(canned_response={"route": "BOM-DEL", "confidence": 0.8})

    await provider.complete(
        system_instructions="sys1", context={}, task="t1",
        available_tools=[], output_schema=_Recommendation,
    )
    await provider.complete(
        system_instructions="sys2", context={}, task="t2",
        available_tools=[], output_schema=_Recommendation,
    )

    assert len(provider.calls) == 2
    assert provider.calls[0]["task"] == "t1"
    assert provider.calls[1]["task"] == "t2"

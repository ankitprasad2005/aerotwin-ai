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

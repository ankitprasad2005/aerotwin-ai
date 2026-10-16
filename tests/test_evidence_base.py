import pytest
from pydantic import ValidationError

from app.evidence import catalog
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.reliability import SOURCE_RELIABILITY


def item(**overrides):
    base = dict(id="a", source="web", kind="web", title="t", url=None, fetched_at=None, reliability=0.4, content="x")
    return EvidenceItem(**{**base, **overrides})


def test_valid_item_accepts_string_and_dict_content():
    assert item(content="text").content == "text"
    assert item(content={"k": [1]}).content == {"k": [1]}


@pytest.mark.parametrize("reliability", [-0.01, 1.01, 5])
def test_reliability_out_of_bounds_rejected(reliability):
    with pytest.raises(ValidationError):
        item(reliability=reliability)


@pytest.mark.parametrize("reliability", [0, 1, 0.5])
def test_reliability_bounds_inclusive(reliability):
    assert item(reliability=reliability).reliability == reliability


def test_unknown_source_or_kind_rejected():
    with pytest.raises(ValidationError):
        item(source="twitter")
    with pytest.raises(ValidationError):
        item(kind="rumour")


def test_request_is_a_plain_dataclass():
    request = EvidenceRequest(agent_type="CARGO", objective="o", route=None, previous_results=[])
    assert request.route is None


def test_source_reliability_values():
    assert SOURCE_RELIABILITY["eia_brent"] == 0.9
    expected = {
        "dgca": 0.9, "eia_jet_fuel": 0.9, "fx": 0.95, "openflights": 0.7, "web": 0.4, "aviation_weather": 0.9, "open_meteo": 0.8,
        "faa_airworthiness_directives": 0.95, "world_bank": 0.85, "india_holidays": 0.95,
    }
    assert SOURCE_RELIABILITY.items() >= expected.items()


def test_catalog_has_exactly_the_known_providers():
    assert "brent_price" in catalog.EVIDENCE_PROVIDERS
    assert set(catalog.EVIDENCE_PROVIDERS) >= {
        "market_competition", "fuel_price", "fx_rate", "dgca_market", "web_search", "weather_observation", "weather_forecast",
        "airworthiness_directives", "weather_taf", "world_bank_demand", "world_bank_freight", "india_holidays",
    }


@pytest.mark.parametrize("name", [
    "market_competition", "fuel_price", "fx_rate", "dgca_market", "web_search", "weather_observation", "weather_forecast",
    "airworthiness_directives", "weather_taf",
        "world_bank_demand", "world_bank_freight",
])
async def test_stub_providers_return_empty_list(db_session, name):
    request = EvidenceRequest(agent_type="NETWORK", objective="o", route="BOM-DEL", previous_results=[])
    assert await catalog.EVIDENCE_PROVIDERS[name](db_session, request) == []

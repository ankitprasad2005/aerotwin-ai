import pytest
from pydantic import ValidationError

from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.registry import AGENT_REGISTRY
from app.agents.schemas import CITED_SOURCES_DESCRIPTION, WeatherRecommendation
from app.agents.weather_agent import WEATHER_AGENT_SPEC
from app.context.engine import AGENT_TASKS, AGENT_TOOLS, build_context_payload
from app.seed.seed import run_seed
from tests.weather_data import add_weather


def _weather(**overrides):
    fields = dict(
        route="BOM-DEL", origin_flight_category="IFR", destination_flight_category="MVFR", weather_risk="HIGH",
        disruption_days_next_7=3, confidence=0.8, risks=["low visibility"], reasoning="r", cited_sources=[],
    )
    fields.update(overrides)
    return WeatherRecommendation(**fields)


def test_spec_shape():
    spec = WEATHER_AGENT_SPEC
    assert AGENT_REGISTRY["WEATHER"] is spec
    assert spec.agent_type == "WEATHER" and spec.depends_on == ("NETWORK",)
    assert spec.tool_name == "query_weather_conditions" == AGENT_TOOLS["WEATHER"][0]
    assert spec.task_description == AGENT_TASKS["WEATHER"]
    assert spec.output_schema is WeatherRecommendation and spec.entities_key == "weather"
    assert spec.evidence_providers == ("weather_observation", "weather_forecast", "web_search", "weather_taf")


def test_instructions_pin_the_route_and_the_precomputed_values():
    text = WEATHER_AGENT_SPEC.system_instructions
    assert "`route` of the NETWORK entry" in text and "never substitute a different one" in text
    assert "copy" in text and "weather_risk" in text and "disruption_days_next_7" in text
    assert "never recompute or invent" in text
    assert text.endswith(EVIDENCE_GUIDANCE)


def test_schema_has_exactly_the_contract_fields():
    assert list(WeatherRecommendation.model_fields) == [
        "route", "origin_flight_category", "destination_flight_category", "weather_risk", "disruption_days_next_7",
        "confidence", "risks", "reasoning", "cited_sources",
    ]
    fields = WeatherRecommendation.model_fields
    assert fields["cited_sources"].description == CITED_SOURCES_DESCRIPTION
    for name in ("origin_flight_category", "destination_flight_category", "weather_risk", "disruption_days_next_7"):
        assert "Copy" in fields[name].description or "copy" in fields[name].description
    assert "required" in WeatherRecommendation.model_json_schema() and (
        "cited_sources" in WeatherRecommendation.model_json_schema()["required"]
    )


def test_recommendation_round_trip():
    rec = _weather()
    assert rec.model_dump()["disruption_days_next_7"] == 3 and rec.weather_risk == "HIGH"
    assert _weather(origin_flight_category="UNKNOWN", destination_flight_category="LIFR", risks=[]).risks == []


@pytest.mark.parametrize("field,value", [
    ("origin_flight_category", "FOGGY"), ("destination_flight_category", "vfr"), ("weather_risk", "SEVERE"),
    ("weather_risk", "UNKNOWN"), ("confidence", -0.1), ("confidence", 1.1), ("disruption_days_next_7", "many"),
])
def test_recommendation_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        _weather(**{field: value})


@pytest.mark.parametrize("missing", list(WeatherRecommendation.model_fields))
def test_recommendation_requires_every_field(missing):
    fields = _weather().model_dump()
    del fields[missing]
    with pytest.raises(ValidationError):
        WeatherRecommendation(**fields)


async def test_tool_fn_and_context_run_against_the_seeded_db(db_session):
    await run_seed(db_session)
    await add_weather(db_session, observations={"BOM": "IFR", "DEL": "VFR"}, forecasts={"BOM": {}, "DEL": {}})

    context = await build_context_payload(
        db_session, objective="x", spec=WEATHER_AGENT_SPEC, previous_results=[{"agent_type": "NETWORK", "route": "BOM-DEL"}],
    )

    routes = {r["route"]: r for r in context["entities"]["weather"]["routes"]}
    assert routes["BOM-DEL"]["weather_risk"] == "HIGH" and routes["BOM-DEL"]["origin_flight_category"] == "IFR"
    assert context["available_tools"] == ["query_weather_conditions"]
    assert {i["id"].split(":")[0] for i in context["evidence"] if i["kind"] == "dataset"} == {"metar", "forecast"}
    assert all(i["content"]["airport"] in ("BOM", "DEL") for i in context["evidence"] if i["kind"] == "dataset")

import copy

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.decision_weights import profile_out, router
from app.api.deps import get_db
from app.decision.weights import DEFAULT_WEIGHTS
from app.models.external import DecisionWeightProfile


def _client(db_session):
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _body(**changes):
    body = copy.deepcopy(DEFAULT_WEIGHTS.model_dump())
    body.update(changes)
    return body


async def test_get_returns_defaults_without_a_profile(db_session):
    async with _client(db_session) as client:
        response = await client.get("/api/decision-weights")

    assert response.status_code == 200
    body = response.json()
    assert body.pop("updated_at") is None
    assert body == DEFAULT_WEIGHTS.model_dump()


async def test_put_upserts_and_get_reads_it_back(db_session):
    async with _client(db_session) as client:
        created = await client.put("/api/decision-weights", json=_body(profit_scale_usd=2500))
        updated = await client.put("/api/decision-weights", json=_body(profit_scale_usd=7500))
        fetched = await client.get("/api/decision-weights")

    assert created.status_code == 200 and created.json()["profit_scale_usd"] == 2500
    assert created.json()["updated_at"] is not None
    assert updated.json()["profit_scale_usd"] == 7500
    assert fetched.json()["profit_scale_usd"] == 7500
    profiles = (await db_session.execute(select(DecisionWeightProfile))).scalars().all()
    assert len(profiles) == 1 and profiles[0].name == "default"


def _mutated(path, value):
    body = _body()
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return body


@pytest.mark.parametrize(
    "body",
    [
        _mutated(("factors", "profit"), -0.1),
        _mutated(("agent_confidence", "CREW"), -1),
        _body(factors={key: 0 for key in DEFAULT_WEIGHTS.factors}),
        _body(agent_confidence={key: 0 for key in DEFAULT_WEIGHTS.agent_confidence}),
        _mutated(("factors", "bogus"), 1),
        _body(factors={"profit": 1}),
        _body(agent_confidence={"NETWORK": 1}),
        _body(thresholds={"recommend": 70}),
        _body(thresholds={"recommend": 50, "review": 50}),
        _body(thresholds={"recommend": 40, "review": 60}),
        _body(thresholds={"recommend": 101, "review": 10}),
        _body(thresholds={"recommend": 70, "review": -1}),
        _body(profit_scale_usd=0),
        _body(profit_scale_usd=-1),
        _body(profit_scale_usd="lots"),
        {k: v for k, v in _body().items() if k != "profit_scale_usd"},
        {k: v for k, v in _body().items() if k != "factors"},
        [],
    ],
)
async def test_put_rejects_invalid_bodies_with_422(db_session, body):
    async with _client(db_session) as client:
        response = await client.put("/api/decision-weights", json=body)

    assert response.status_code == 422
    assert (await db_session.execute(select(DecisionWeightProfile))).scalars().all() == []


async def test_put_accepts_edge_thresholds(db_session):
    async with _client(db_session) as client:
        response = await client.put("/api/decision-weights", json=_body(thresholds={"recommend": 100, "review": 0}))

    assert response.status_code == 200


async def test_put_ignores_a_client_supplied_updated_at(db_session):
    async with _client(db_session) as client:
        response = await client.put("/api/decision-weights", json={**_body(), "updated_at": "2001-01-01T00:00:00Z"})

    assert response.status_code == 200
    assert not response.json()["updated_at"].startswith("2001")


def test_profile_out_falls_back_to_defaults_for_an_invalid_stored_profile():
    out = profile_out(DecisionWeightProfile(name="default", weights={"nonsense": True}))

    assert out.updated_at is None
    assert out.factors == DEFAULT_WEIGHTS.factors

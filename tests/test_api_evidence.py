import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.evidence import router as evidence_router
from app.models.observability import (
    AgentExecution, ContextSnapshot, Event, OrchestrationRun, RunIteration,
)

ITEM = {
    "id": "fuel:eia:2026-10-10", "source": "eia_jet_fuel", "kind": "dataset", "title": "Jet fuel",
    "url": None, "fetched_at": None, "reliability": 0.9, "content": {"usd_per_gallon": 2.1},
}


def _client(db_session) -> AsyncClient:
    app = FastAPI()
    app.include_router(evidence_router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _run(db_session):
    run = OrchestrationRun(objective="x", status="COMPLETED")
    db_session.add(run)
    await db_session.flush()
    return run


async def _execution(db_session, run, agent_type, *, iteration=None, context=None, recommendation=None):
    execution = AgentExecution(
        run_id=run.id, agent_type=agent_type, status="COMPLETED", task="t",
        iteration_id=iteration.id if iteration else None,
    )
    db_session.add(execution)
    await db_session.flush()
    if context is not None:
        db_session.add(ContextSnapshot(agent_execution_id=execution.id, payload=context))
    if recommendation is not None:
        db_session.add(Event(
            run_id=run.id, agent_execution_id=execution.id, event_type="agent.completed", severity="INFO",
            payload={"recommendation": recommendation},
        ))
    await db_session.flush()
    return execution


async def test_unknown_run_is_404(db_session):
    async with _client(db_session) as client:
        response = await client.get(f"/api/runs/{uuid.uuid4()}/evidence")
    assert response.status_code == 404
    assert response.json()["detail"] == "run not found"


async def test_malformed_run_id_is_422(db_session):
    async with _client(db_session) as client:
        assert (await client.get("/api/runs/not-a-uuid/evidence")).status_code == 422


async def test_run_without_executions_returns_empty_list(db_session):
    run = await _run(db_session)
    async with _client(db_session) as client:
        response = await client.get(f"/api/runs/{run.id}/evidence")
    assert response.status_code == 200 and response.json() == []


async def test_returns_evidence_unavailable_and_citations_per_execution_in_order(db_session):
    run = await _run(db_session)
    iteration = RunIteration(run_id=run.id, sequence=2, objective="x", status="COMPLETED")
    db_session.add(iteration)
    await db_session.flush()
    first = await _execution(
        db_session, run, "NETWORK", iteration=iteration,
        context={"evidence": [ITEM], "evidence_unavailable": ["web_search: timed out"]},
        recommendation={"route": "BOM-DEL", "cited_sources": [ITEM["id"]]},
    )
    second = await _execution(
        db_session, run, "FLEET", iteration=iteration,
        context={"evidence": [], "evidence_unavailable": []},
        recommendation={"cited_sources": []},
    )

    async with _client(db_session) as client:
        response = await client.get(f"/api/runs/{run.id}/evidence")

    assert response.status_code == 200
    assert response.json() == [
        {
            "agent_execution_id": str(first.id), "agent_type": "NETWORK", "iteration": 2,
            "evidence": [ITEM], "evidence_unavailable": ["web_search: timed out"], "cited_sources": [ITEM["id"]],
        },
        {
            "agent_execution_id": str(second.id), "agent_type": "FLEET", "iteration": 2,
            "evidence": [], "evidence_unavailable": [], "cited_sources": [],
        },
    ]


async def test_execution_without_snapshot_or_recommendation_gets_empty_fields(db_session):
    run = await _run(db_session)
    execution = await _execution(db_session, run, "CREW")

    async with _client(db_session) as client:
        body = (await client.get(f"/api/runs/{run.id}/evidence")).json()

    assert body == [{
        "agent_execution_id": str(execution.id), "agent_type": "CREW", "iteration": None,
        "evidence": [], "evidence_unavailable": [], "cited_sources": [],
    }]


async def test_snapshot_from_before_evidence_existed_is_tolerated(db_session):
    run = await _run(db_session)
    await _execution(db_session, run, "CARGO", context={"objective": "x"}, recommendation={"route": "BOM-DEL"})

    async with _client(db_session) as client:
        body = (await client.get(f"/api/runs/{run.id}/evidence")).json()

    assert body[0]["evidence"] == [] and body[0]["evidence_unavailable"] == [] and body[0]["cited_sources"] == []


@pytest.mark.parametrize("context", [
    {"evidence": "oops", "evidence_unavailable": "oops"},
    {"evidence": None, "evidence_unavailable": [1, None, "ok: down"]},
])
async def test_malformed_snapshot_values_are_sanitised(db_session, context):
    run = await _run(db_session)
    await _execution(db_session, run, "NETWORK", context=context, recommendation={"cited_sources": "bad"})

    async with _client(db_session) as client:
        body = (await client.get(f"/api/runs/{run.id}/evidence")).json()

    assert body[0]["evidence"] == []
    assert body[0]["evidence_unavailable"] == (["ok: down"] if isinstance(context["evidence_unavailable"], list) else [])
    assert body[0]["cited_sources"] == []


async def test_only_this_runs_executions_are_returned(db_session):
    run = await _run(db_session)
    other = await _run(db_session)
    await _execution(db_session, run, "NETWORK", context={"evidence": [ITEM]})
    await _execution(db_session, other, "FLEET", context={"evidence": []})

    async with _client(db_session) as client:
        body = (await client.get(f"/api/runs/{run.id}/evidence")).json()

    assert [e["agent_type"] for e in body] == ["NETWORK"]

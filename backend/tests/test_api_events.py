from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.events import router as events_router
from app.models.observability import Event, OrchestrationRun, OrchestrationRunStatus


def _build_app(db_session):
    app = FastAPI()
    app.include_router(events_router)

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return app


async def _seed_events(db_session):
    run_a = OrchestrationRun(objective="a", status=OrchestrationRunStatus.RUNNING.value)
    run_b = OrchestrationRun(objective="b", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add_all([run_a, run_b])
    await db_session.flush()

    db_session.add_all(
        [
            Event(run_id=run_a.id, event_type="orchestration.started", severity="INFO", payload={}),
            Event(run_id=run_a.id, event_type="llm.request", severity="INFO", payload={}),
            Event(run_id=run_a.id, event_type="tool.failed", severity="ERROR", payload={}),
            Event(run_id=run_b.id, event_type="orchestration.started", severity="INFO", payload={}),
        ]
    )
    await db_session.flush()
    return run_a, run_b


async def test_list_events_returns_all_by_default(db_session):
    await _seed_events(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events")

    assert response.status_code == 200
    assert len(response.json()) == 4


async def test_list_events_filters_by_run_id(db_session):
    run_a, run_b = await _seed_events(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events", params={"run_id": str(run_a.id)})

    assert len(response.json()) == 3


async def test_list_events_filters_by_event_type(db_session):
    await _seed_events(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events", params={"event_type": "orchestration.started"})

    assert len(response.json()) == 2


async def test_list_events_filters_by_severity(db_session):
    await _seed_events(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events", params={"severity": "ERROR"})

    assert len(response.json()) == 1
    assert response.json()[0]["event_type"] == "tool.failed"


async def test_list_events_respects_limit_pagination(db_session):
    await _seed_events(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events", params={"limit": 2})

    assert len(response.json()) == 2


async def test_list_events_empty_db_returns_empty_list(db_session):
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events")

    assert response.json() == []


async def test_list_events_filters_by_agent_execution_id(db_session):
    run_a, _ = await _seed_events(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events", params={"agent_execution_id": str(run_a.id)})

    # run_a.id is not actually an agent_execution_id (no events have one set in seed data),
    # so filtering by it should return zero results, proving the filter is applied.
    assert response.json() == []


async def test_list_events_filters_by_entity_type(db_session):
    run_a, _ = await _seed_events(db_session)
    app = _build_app(db_session)

    extra_event = Event(
        run_id=run_a.id, event_type="digital_twin.updated", severity="INFO",
        entity_type="Aircraft", entity_id="VT-AER1", payload={},
    )
    db_session.add(extra_event)
    await db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events", params={"entity_type": "Aircraft"})

    assert len(response.json()) == 1
    assert response.json()[0]["entity_id"] == "VT-AER1"


async def test_list_events_limit_above_max_returns_422(db_session):
    await _seed_events(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events", params={"limit": 5000})

    assert response.status_code == 422

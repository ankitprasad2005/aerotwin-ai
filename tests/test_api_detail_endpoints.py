import uuid

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.agent_executions import router as agent_executions_router
from app.api.decisions import router as decisions_router
from app.api.deps import get_db
from app.api.llm_executions import router as llm_executions_router
from app.api.tool_executions import router as tool_executions_router
from app.models.observability import (
    AgentExecution, AgentExecutionStatus, ContextSnapshot, Decision, Event, LLMExecution,
    OrchestrationRun, OrchestrationRunStatus, ToolExecution,
)

RECOMMENDATION = {
    "route": "BOM-DEL", "action": "INCREASE_FREQUENCY", "expected_profit_impact": 17163.0,
    "expected_revenue_impact": 26163.0, "expected_cost_impact": 9000.0, "confidence": 0.9,
    "risks": ["crew scheduling"], "reasoning": "Weekly demand exceeds current capacity.", "cited_sources": [],
}


def _build_app(db_session):
    app = FastAPI()
    for r in (agent_executions_router, llm_executions_router, tool_executions_router, decisions_router):
        app.include_router(r)

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return app


async def _seed_full_chain(db_session):
    run = OrchestrationRun(objective="x", status=OrchestrationRunStatus.COMPLETED.value)
    db_session.add(run)
    await db_session.flush()

    execution = AgentExecution(
        run_id=run.id, agent_type="NETWORK", status=AgentExecutionStatus.COMPLETED.value,
        task="t", elapsed_ms=4200, total_tokens=180,
    )
    db_session.add(execution)
    await db_session.flush()

    snapshot = ContextSnapshot(agent_execution_id=execution.id, payload={"objective": "x"})
    llm_execution = LLMExecution(
        agent_execution_id=execution.id, provider="openai", model="gpt-4o-mini", request_id="req-1",
        system_instructions="sys", context={"a": 1}, task="t", available_tools=["query_route_profitability"],
        model_parameters={}, raw_response={"id": "req-1"}, input_tokens=100, output_tokens=50,
        total_tokens=150, estimated_cost=0.001, duration_ms=4200, retry_count=0, status="COMPLETED",
    )
    tool_execution = ToolExecution(
        agent_execution_id=execution.id, tool_name="query_route_profitability", arguments={},
        result={"routes": []}, data_source="postgres", duration_ms=80,
    )
    decision = Decision(
        run_id=run.id, summary="Increase BOM-DEL frequency", expected_profit_impact=1.0,
        expected_revenue_impact=2.0, expected_cost_impact=3.0, confidence=0.8, risks=[],
        constraints_checked=[], validation_result={"schema": "PASS"}, status="RECOMMENDED",
        agents_involved=[str(execution.id)],
    )
    completed_event = Event(
        run_id=run.id, agent_execution_id=execution.id, event_type="agent.completed",
        severity="INFO", payload={"recommendation": RECOMMENDATION},
    )
    db_session.add_all([snapshot, llm_execution, tool_execution, decision, completed_event])
    await db_session.flush()
    return execution, llm_execution, tool_execution, decision


async def test_get_agent_execution_detail_includes_context_llm_and_tools(db_session):
    execution, llm_execution, tool_execution, decision = await _seed_full_chain(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/agent-executions/{execution.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["context_snapshot"]["payload"] == {"objective": "x"}
    assert body["llm_execution"]["provider"] == "openai"
    assert len(body["tool_executions"]) == 1
    assert body["recommendation"] == RECOMMENDATION


async def test_get_agent_execution_detail_missing_returns_404(db_session):
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/agent-executions/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_agent_execution_detail_without_llm_or_tools_returns_none_and_empty_list(db_session):
    run = OrchestrationRun(objective="x", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()

    execution = AgentExecution(
        run_id=run.id, agent_type="FLEET", status=AgentExecutionStatus.WAITING_FOR_TOOL.value,
        task="t", elapsed_ms=None, total_tokens=None,
    )
    db_session.add(execution)
    await db_session.flush()

    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/agent-executions/{execution.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["context_snapshot"] is None
    assert body["llm_execution"] is None
    assert body["tool_executions"] == []
    assert body["recommendation"] is None  # the agent hasn't completed yet


async def test_get_llm_execution_detail(db_session):
    execution, llm_execution, tool_execution, decision = await _seed_full_chain(db_session)
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/llm-executions/{llm_execution.id}")
    assert response.status_code == 200
    assert response.json()["model"] == "gpt-4o-mini"


async def test_get_llm_execution_detail_missing_returns_404(db_session):
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/llm-executions/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_tool_execution_detail(db_session):
    execution, llm_execution, tool_execution, decision = await _seed_full_chain(db_session)
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/tool-executions/{tool_execution.id}")
    assert response.status_code == 200
    assert response.json()["tool_name"] == "query_route_profitability"


async def test_get_tool_execution_detail_missing_returns_404(db_session):
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/tool-executions/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_decision_detail(db_session):
    execution, llm_execution, tool_execution, decision = await _seed_full_chain(db_session)
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/decisions/{decision.id}")
    assert response.status_code == 200
    assert response.json()["summary"] == "Increase BOM-DEL frequency"


async def test_get_decision_detail_missing_returns_404(db_session):
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/decisions/{uuid.uuid4()}")
    assert response.status_code == 404

import uuid

from sqlalchemy import select

from app.models.observability import (
    AgentExecution,
    AgentExecutionStatus,
    AgentMessage,
    ContextSnapshot,
    Decision,
    Event,
    EventSeverity,
    LLMExecution,
    OrchestrationRun,
    OrchestrationRunStatus,
    ToolExecution,
)


async def test_orchestration_run_and_agent_execution_chain(db_session):
    run = OrchestrationRun(objective="Improve profitability", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()

    execution = AgentExecution(
        run_id=run.id,
        agent_type="NETWORK",
        status=AgentExecutionStatus.RUNNING.value,
        task="Identify profitable route frequency changes.",
    )
    db_session.add(execution)
    await db_session.flush()

    snapshot = ContextSnapshot(agent_execution_id=execution.id, payload={"objective": run.objective})
    llm_exec = LLMExecution(
        agent_execution_id=execution.id,
        provider="openai",
        model="gpt-4o-mini",
        request_id="req-1",
        system_instructions="You are the network agent.",
        context={"objective": run.objective},
        task=execution.task,
        available_tools=["query_route_profitability"],
        model_parameters={"temperature": 0.2},
        raw_response={"choices": []},
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        estimated_cost=0.001,
        duration_ms=4200,
        retry_count=0,
        status="COMPLETED",
    )
    tool_exec = ToolExecution(
        agent_execution_id=execution.id,
        tool_name="query_route_profitability",
        arguments={"route_code": "BOM-DEL"},
        result={"profit_margin": 0.12},
        data_source="postgres",
        duration_ms=80,
    )
    db_session.add_all([snapshot, llm_exec, tool_exec])
    await db_session.flush()

    message = AgentMessage(
        run_id=run.id,
        context_id=snapshot.id,
        sender="NETWORK_AGENT",
        receiver="ORCHESTRATOR",
        message_type="RECOMMENDATION",
        payload={"route": "BOM-DEL", "action": "INCREASE_FREQUENCY"},
    )
    decision = Decision(
        run_id=run.id,
        summary="Increase BOM -> DEL frequency",
        expected_profit_impact=125000.0,
        expected_revenue_impact=300000.0,
        expected_cost_impact=175000.0,
        confidence=0.82,
        risks=["fuel price volatility"],
        constraints_checked=["aircraft_availability"],
        validation_result={"schema": "PASS", "constraints": "PASS", "conflicts": [], "risk": "MEDIUM"},
        status="RECOMMENDED",
        agents_involved=[str(execution.id)],
    )
    event = Event(
        run_id=run.id,
        agent_execution_id=execution.id,
        event_type="agent.completed",
        severity=EventSeverity.INFO.value,
        payload={"summary": "Network agent completed"},
    )
    db_session.add_all([message, decision, event])
    await db_session.flush()

    result = await db_session.execute(select(Event).where(Event.run_id == run.id))
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "agent.completed"


async def test_agent_execution_status_enum_has_all_spec_states():
    expected = {
        "WAITING", "QUEUED", "RUNNING", "WAITING_FOR_LLM", "WAITING_FOR_TOOL",
        "COMPLETED", "FAILED", "RETRYING", "BLOCKED",
    }
    assert {s.value for s in AgentExecutionStatus} == expected


async def test_event_defaults_to_info_severity(db_session):
    run = OrchestrationRun(objective="x", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()

    event = Event(run_id=run.id, event_type="orchestration.started", payload={})
    db_session.add(event)
    await db_session.flush()

    assert event.severity == EventSeverity.INFO.value


async def test_event_can_have_warn_severity(db_session):
    run = OrchestrationRun(objective="x", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()

    event = Event(run_id=run.id, event_type="tool.retrying", severity=EventSeverity.WARN.value, payload={})
    db_session.add(event)
    await db_session.flush()

    assert event.severity == EventSeverity.WARN.value

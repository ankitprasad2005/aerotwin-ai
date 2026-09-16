from app.api.recommendations import recommendations_by_execution
from app.models.observability import (
    AgentExecution, AgentExecutionStatus, Event, OrchestrationRun, OrchestrationRunStatus,
)

RECOMMENDATION = {"route": "BOM-DEL", "action": "MAINTAIN"}


async def _make_execution(db_session):
    run = OrchestrationRun(objective="x", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()
    execution = AgentExecution(
        run_id=run.id, agent_type="NETWORK", status=AgentExecutionStatus.COMPLETED.value, task="t"
    )
    db_session.add(execution)
    await db_session.flush()
    return run, execution


async def test_no_execution_ids_returns_empty_without_querying(db_session):
    assert await recommendations_by_execution(db_session, []) == {}


async def test_returns_the_recommendation_from_the_completed_event(db_session):
    run, execution = await _make_execution(db_session)
    db_session.add(
        Event(
            run_id=run.id, agent_execution_id=execution.id, event_type="agent.completed",
            severity="INFO", payload={"recommendation": RECOMMENDATION},
        )
    )
    await db_session.flush()

    assert await recommendations_by_execution(db_session, [execution.id]) == {execution.id: RECOMMENDATION}


async def test_ignores_a_completed_event_whose_payload_has_no_recommendation(db_session):
    """Defensive: the payload shape is the runner's, not a schema-enforced column."""
    run, execution = await _make_execution(db_session)
    db_session.add(
        Event(
            run_id=run.id, agent_execution_id=execution.id, event_type="agent.completed",
            severity="INFO", payload={"note": "no recommendation here"},
        )
    )
    await db_session.flush()

    assert await recommendations_by_execution(db_session, [execution.id]) == {}

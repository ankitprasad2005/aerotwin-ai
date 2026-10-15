from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.stats import (
    SERIES_DAYS, decision_summary, duration_ms, last_days, p95, run_row, verdict_counts, zero_filled,
)
from app.api.stats import router
from app.models.external import FuelPrice, FxRate
from app.models.observability import (
    AgentExecution, Decision, LLMExecution, OrchestrationRun, RunIteration,
)

NOW = datetime.now(timezone.utc)


def _client(db_session):
    app = FastAPI()
    app.include_router(router)

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _run(db, *, status="COMPLETED", seconds=2.0, created=None, objective="obj"):
    created = created or NOW - timedelta(minutes=5)
    run = OrchestrationRun(
        objective=objective, status=status, created_at=created,
        completed_at=created + timedelta(seconds=seconds) if status != "RUNNING" else None,
    )
    db.add(run)
    await db.flush()
    return run


async def _llm(db, run, tokens, *, created=None):
    execution = AgentExecution(run_id=run.id, agent_type="NETWORK", status="COMPLETED", task="t")
    db.add(execution)
    await db.flush()
    db.add(LLMExecution(
        agent_execution_id=execution.id, provider="p", model="m", request_id="r", system_instructions="s",
        context={}, task="t", available_tools=[], model_parameters={}, raw_response={},
        input_tokens=tokens, output_tokens=0, total_tokens=tokens, duration_ms=1, status="OK",
        created_at=created or NOW,
    ))
    await db.flush()


async def _decision(db, run, *, verdict="RECOMMEND", score=80.0, created=None, summary="Increase BOM-DEL frequency"):
    result = {"risk": "LOW"}
    if verdict is not None:
        result.update(verdict=verdict, score=score)
    db.add(Decision(
        run_id=run.id, summary=summary, expected_profit_impact=100.0, expected_revenue_impact=200.0,
        expected_cost_impact=100.0, confidence=0.8, risks=[], constraints_checked=[],
        validation_result=result, created_at=created or NOW,
    ))
    await db.flush()


# --- pure helpers ------------------------------------------------------------------------------

def test_p95_empty_is_none():
    assert p95([]) is None


def test_p95_single_value():
    assert p95([42]) == 42


def test_p95_nearest_rank():
    assert p95(range(1, 101)) == 95  # 100 values -> rank 95
    assert p95(range(1, 21)) == 19  # 20 values -> rank 19
    assert p95([5, 1, 3]) == 5  # unordered input; rank ceil(2.85) = 3
    assert p95([1, 2]) == 2


def test_p95_ignores_input_order_and_is_not_the_mean():
    values = [10] * 99 + [10_000]
    assert p95(values) == 10
    assert p95(reversed(values)) == 10


def test_duration_ms():
    start = NOW
    assert duration_ms(start, start + timedelta(seconds=1.5)) == 1500
    assert duration_ms(start, start) == 0
    assert duration_ms(start, None) is None
    assert duration_ms(None, start) is None


def test_last_days_is_oldest_first_and_ends_today():
    days = last_days(date(2026, 10, 15))
    assert len(days) == SERIES_DAYS == 14
    assert days[0] == date(2026, 10, 2) and days[-1] == date(2026, 10, 15)


def test_last_days_crosses_month_and_year_boundaries():
    assert last_days(date(2027, 1, 3), 5) == [date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 1),
                                              date(2027, 1, 2), date(2027, 1, 3)]


def test_zero_filled_fills_gaps_and_drops_out_of_window_days():
    today = date(2026, 10, 15)
    series = zero_filled({today: 3, date(2026, 10, 10): 1, date(2026, 9, 1): 99}, today, "count")

    assert len(series) == 14
    assert series[-1] == {"date": "2026-10-15", "count": 3}
    assert series[-6] == {"date": "2026-10-10", "count": 1}
    assert sum(point["count"] for point in series) == 4
    assert zero_filled({}, today, "tokens")[0] == {"date": "2026-10-02", "tokens": 0}


def test_verdict_counts_zero_filled_and_skips_unknown():
    assert verdict_counts([]) == {"RECOMMEND": 0, "REVIEW": 0, "REJECT": 0}
    assert verdict_counts([("RECOMMEND", 2), (None, 5), ("MAYBE", 1), ("REJECT", 3)]) == {
        "RECOMMEND": 2, "REVIEW": 0, "REJECT": 3,
    }


def test_decision_summary_none_and_legacy():
    assert decision_summary(None) is None
    legacy = Decision(summary="s", expected_profit_impact=1.0, validation_result={"risk": "LOW"})
    assert decision_summary(legacy) == {
        "summary": "s", "verdict": None, "score": None, "expected_profit_impact": 1.0, "risk": "LOW",
    }
    assert decision_summary(Decision(summary="s", expected_profit_impact=1.0, validation_result=None))["risk"] is None


def test_run_row_for_a_running_run_has_no_duration():
    run = OrchestrationRun(id=None, objective="o", status="RUNNING", created_at=NOW, completed_at=None)
    row = run_row(run, iterations=1, tokens=0, decision=None)

    assert row["duration_ms"] is None and row["decision"] is None and row["completed_at"] is None


# --- GET /api/stats ----------------------------------------------------------------------------

async def test_stats_on_an_empty_database(db_session):
    async with _client(db_session) as client:
        response = await client.get("/api/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["runs_total"] == body["runs_completed"] == body["runs_failed"] == body["runs_running"] == 0
    assert body["p95_run_duration_ms"] is None
    assert body["tokens_total"] == 0 and body["tokens_last_24h"] == 0
    assert body["decisions_by_verdict"] == {"RECOMMEND": 0, "REVIEW": 0, "REJECT": 0}
    assert body["latest_fuel_price"] is None and body["latest_usd_inr"] is None
    assert len(body["runs_per_day"]) == 14 and all(p["count"] == 0 for p in body["runs_per_day"])
    assert len(body["tokens_per_day"]) == 14 and all(p["tokens"] == 0 for p in body["tokens_per_day"])
    assert body["runs_per_day"][-1]["date"] == NOW.date().isoformat()


async def test_stats_counts_runs_by_status_and_p95_with_a_single_run(db_session):
    await _run(db_session, seconds=2.0)
    await _run(db_session, status="FAILED", seconds=100.0)  # failed runs do not count towards p95
    await _run(db_session, status="RUNNING")
    async with _client(db_session) as client:
        body = (await client.get("/api/stats")).json()

    assert (body["runs_total"], body["runs_completed"], body["runs_failed"], body["runs_running"]) == (3, 1, 1, 1)
    assert body["p95_run_duration_ms"] == 2000


async def test_stats_p95_over_many_completed_runs(db_session):
    for second in range(1, 21):
        await _run(db_session, seconds=float(second))
    async with _client(db_session) as client:
        body = (await client.get("/api/stats")).json()

    assert body["p95_run_duration_ms"] == 19000


async def test_stats_tokens_total_last_24h_and_per_day(db_session):
    run = await _run(db_session)
    await _llm(db_session, run, 100)
    await _llm(db_session, run, 50, created=NOW - timedelta(hours=30))
    await _llm(db_session, run, 7, created=NOW - timedelta(days=40))  # outside the 14-day window
    async with _client(db_session) as client:
        body = (await client.get("/api/stats")).json()

    assert body["tokens_total"] == 157
    assert body["tokens_last_24h"] == 100
    per_day = {p["date"]: p["tokens"] for p in body["tokens_per_day"]}
    assert per_day[NOW.date().isoformat()] == 100
    assert per_day[(NOW - timedelta(hours=30)).date().isoformat()] == 50
    assert sum(per_day.values()) == 150


async def test_stats_runs_per_day_is_zero_filled(db_session):
    await _run(db_session, created=NOW)
    await _run(db_session, created=NOW)
    await _run(db_session, created=NOW - timedelta(days=3))
    await _run(db_session, created=NOW - timedelta(days=20))
    async with _client(db_session) as client:
        body = (await client.get("/api/stats")).json()

    per_day = {p["date"]: p["count"] for p in body["runs_per_day"]}
    assert per_day[NOW.date().isoformat()] == 2
    assert per_day[(NOW - timedelta(days=3)).date().isoformat()] == 1
    assert sum(per_day.values()) == 3
    assert [p["date"] for p in body["runs_per_day"]] == sorted(per_day)


async def test_stats_decisions_by_verdict(db_session):
    run = await _run(db_session)
    for verdict in ("RECOMMEND", "RECOMMEND", "REVIEW", "REJECT", None):
        await _decision(db_session, run, verdict=verdict)
    async with _client(db_session) as client:
        body = (await client.get("/api/stats")).json()

    assert body["decisions_by_verdict"] == {"RECOMMEND": 2, "REVIEW": 1, "REJECT": 1}


async def test_stats_latest_fuel_and_fx(db_session):
    db_session.add_all([
        FuelPrice(series="s", price_date=date(2026, 10, 1), usd_per_gallon=2.0),
        FuelPrice(series="s", price_date=date(2026, 10, 9), usd_per_gallon=2.5),
        FxRate(base="USD", quote="INR", rate_date=date(2026, 10, 8), rate=83.0),
        FxRate(base="USD", quote="INR", rate_date=date(2026, 10, 2), rate=82.0),
        FxRate(base="USD", quote="EUR", rate_date=date(2026, 10, 14), rate=0.9),  # not USD/INR
        FxRate(base="EUR", quote="INR", rate_date=date(2026, 10, 14), rate=90.0),
    ])
    await db_session.flush()
    async with _client(db_session) as client:
        body = (await client.get("/api/stats")).json()

    assert body["latest_fuel_price"] == {"date": "2026-10-09", "usd_per_gallon": 2.5}
    assert body["latest_usd_inr"] == {"date": "2026-10-08", "rate": 83.0}


# --- GET /api/stats/runs -----------------------------------------------------------------------

async def test_stats_runs_empty(db_session):
    async with _client(db_session) as client:
        response = await client.get("/api/stats/runs")

    assert response.status_code == 200 and response.json() == []


async def test_stats_runs_rows_newest_first_with_latest_decision(db_session):
    older = await _run(db_session, created=NOW - timedelta(hours=2), objective="older", seconds=3)
    newer = await _run(db_session, created=NOW - timedelta(hours=1), objective="newer", seconds=1.5)
    running = await _run(db_session, status="RUNNING", created=NOW, objective="running")
    db_session.add_all([
        RunIteration(run_id=older.id, sequence=1, objective="a", status="COMPLETED"),
        RunIteration(run_id=older.id, sequence=2, objective="b", status="COMPLETED"),
        RunIteration(run_id=newer.id, sequence=1, objective="a", status="COMPLETED"),
    ])
    await _llm(db_session, older, 30)
    await _llm(db_session, older, 12)
    await _llm(db_session, newer, 5)
    await _decision(db_session, older, verdict="REVIEW", score=50.0, created=NOW - timedelta(hours=2), summary="first")
    await _decision(db_session, older, verdict="RECOMMEND", score=88.5, created=NOW - timedelta(hours=1), summary="second")
    async with _client(db_session) as client:
        rows = (await client.get("/api/stats/runs")).json()

    assert [r["objective"] for r in rows] == ["running", "newer", "older"]
    by_objective = {r["objective"]: r for r in rows}
    assert by_objective["older"]["iterations"] == 2
    assert by_objective["older"]["total_tokens"] == 42
    assert by_objective["older"]["duration_ms"] == 3000
    assert by_objective["older"]["decision"] == {
        "summary": "second", "verdict": "RECOMMEND", "score": 88.5, "expected_profit_impact": 100.0, "risk": "LOW",
    }
    assert by_objective["newer"]["decision"] is None
    assert by_objective["newer"]["total_tokens"] == 5
    assert by_objective["running"]["status"] == "RUNNING"
    assert by_objective["running"]["duration_ms"] is None
    assert by_objective["running"]["completed_at"] is None
    assert by_objective["running"]["iterations"] == 0 and by_objective["running"]["total_tokens"] == 0
    assert set(rows[0]) == {
        "id", "objective", "status", "created_at", "completed_at", "duration_ms", "total_tokens", "iterations",
        "decision",
    }


async def test_stats_runs_respects_limit(db_session):
    for i in range(5):
        await _run(db_session, created=NOW - timedelta(minutes=i), objective=f"r{i}")
    async with _client(db_session) as client:
        rows = (await client.get("/api/stats/runs", params={"limit": 2})).json()

    assert [r["objective"] for r in rows] == ["r0", "r1"]


@pytest.mark.parametrize("limit", [0, -1, 501, "abc"])
async def test_stats_runs_rejects_bad_limits(db_session, limit):
    async with _client(db_session) as client:
        response = await client.get("/api/stats/runs", params={"limit": limit})

    assert response.status_code == 422


async def test_stats_runs_accepts_boundary_limits(db_session):
    async with _client(db_session) as client:
        assert (await client.get("/api/stats/runs", params={"limit": 1})).status_code == 200
        assert (await client.get("/api/stats/runs", params={"limit": 500})).status_code == 200

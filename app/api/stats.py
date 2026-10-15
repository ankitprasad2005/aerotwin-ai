import math
import uuid
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.external import FuelPrice, FxRate
from app.models.observability import (
    AgentExecution, Decision, LLMExecution, OrchestrationRun, OrchestrationRunStatus, RunIteration,
)

router = APIRouter(prefix="/api/stats", tags=["stats"])

SERIES_DAYS = 14
VERDICTS = ("RECOMMEND", "REVIEW", "REJECT")


# --- pure helpers (kept free of I/O so they are fully unit-testable) ---------------------------

def p95(values: Iterable[float]) -> float | None:
    """The 95th percentile by the nearest-rank method; None for no values."""
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def duration_ms(created_at: datetime | None, completed_at: datetime | None) -> int | None:
    if created_at is None or completed_at is None:
        return None
    return round((completed_at - created_at).total_seconds() * 1000)


def last_days(today: date, days: int = SERIES_DAYS) -> list[date]:
    """The `days` calendar days ending at `today`, oldest first."""
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def zero_filled(counts: Mapping[date, int], today: date, key: str, days: int = SERIES_DAYS) -> list[dict]:
    return [{"date": day.isoformat(), key: int(counts.get(day, 0))} for day in last_days(today, days)]


def verdict_counts(verdicts: Iterable[tuple[str | None, int]]) -> dict[str, int]:
    """Decision counts per verdict; decisions with no (or an unknown) verdict, e.g. legacy rows, are skipped."""
    counts = dict.fromkeys(VERDICTS, 0)
    for verdict, count in verdicts:
        if verdict in counts:
            counts[verdict] += count
    return counts


def decision_summary(decision: Decision | None) -> dict | None:
    if decision is None:
        return None
    result = decision.validation_result or {}
    return {
        "summary": decision.summary,
        "verdict": result.get("verdict"),
        "score": result.get("score"),
        "expected_profit_impact": decision.expected_profit_impact,
        "risk": result.get("risk"),
    }


def run_row(
    run: OrchestrationRun, *, iterations: int, tokens: int, decision: Decision | None
) -> dict:
    return {
        "id": str(run.id),
        "objective": run.objective,
        "status": run.status,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "duration_ms": duration_ms(run.created_at, run.completed_at),
        "total_tokens": tokens,
        "iterations": iterations,
        "decision": decision_summary(decision),
    }


# --- queries -----------------------------------------------------------------------------------

def _utc_date(column):
    return cast(func.timezone("UTC", column), Date)


async def _daily(db: AsyncSession, column, since: datetime, value) -> dict[date, int]:
    day = _utc_date(column).label("day")
    rows = (
        await db.execute(select(day, value).where(column >= since).group_by(day))
    ).all()
    return {row[0]: int(row[1] or 0) for row in rows}


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    today = now.date()
    since = datetime.combine(last_days(today)[0], datetime.min.time(), tzinfo=timezone.utc)

    status_counts = dict(
        (await db.execute(select(OrchestrationRun.status, func.count()).group_by(OrchestrationRun.status))).all()
    )
    completed_runs = (
        await db.execute(
            select(OrchestrationRun.created_at, OrchestrationRun.completed_at).where(
                OrchestrationRun.status == OrchestrationRunStatus.COMPLETED.value,
                OrchestrationRun.completed_at.is_not(None),
            )
        )
    ).all()
    durations = [duration_ms(created, completed) for created, completed in completed_runs]

    tokens_total = (await db.execute(select(func.coalesce(func.sum(LLMExecution.total_tokens), 0)))).scalar_one()
    tokens_24h = (
        await db.execute(
            select(func.coalesce(func.sum(LLMExecution.total_tokens), 0)).where(
                LLMExecution.created_at >= now - timedelta(hours=24)
            )
        )
    ).scalar_one()
    verdict = Decision.validation_result["verdict"].astext.label("verdict")
    verdict_rows = (await db.execute(select(verdict, func.count()).group_by(verdict))).all()
    fuel = (
        await db.execute(select(FuelPrice).order_by(FuelPrice.price_date.desc()).limit(1))
    ).scalar_one_or_none()
    fx = (
        await db.execute(
            select(FxRate).where(FxRate.base == "USD", FxRate.quote == "INR").order_by(FxRate.rate_date.desc()).limit(1)
        )
    ).scalar_one_or_none()
    runs_per_day = await _daily(db, OrchestrationRun.created_at, since, func.count())
    tokens_per_day = await _daily(db, LLMExecution.created_at, since, func.sum(LLMExecution.total_tokens))

    return {
        "runs_total": sum(status_counts.values()),
        "runs_completed": status_counts.get(OrchestrationRunStatus.COMPLETED.value, 0),
        "runs_failed": status_counts.get(OrchestrationRunStatus.FAILED.value, 0),
        "runs_running": status_counts.get(OrchestrationRunStatus.RUNNING.value, 0),
        "p95_run_duration_ms": p95(durations),
        "tokens_total": int(tokens_total),
        "tokens_last_24h": int(tokens_24h),
        "decisions_by_verdict": verdict_counts(verdict_rows),
        "latest_fuel_price": (
            {"date": fuel.price_date.isoformat(), "usd_per_gallon": fuel.usd_per_gallon} if fuel else None
        ),
        "latest_usd_inr": ({"date": fx.rate_date.isoformat(), "rate": fx.rate} if fx else None),
        "runs_per_day": zero_filled(runs_per_day, today, "count"),
        "tokens_per_day": zero_filled(tokens_per_day, today, "tokens"),
    }


@router.get("/runs")
async def get_run_stats(
    limit: int = Query(100, ge=1, le=500), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    runs = (
        await db.execute(select(OrchestrationRun).order_by(OrchestrationRun.created_at.desc()).limit(limit))
    ).scalars().all()
    if not runs:
        return []
    run_ids = [run.id for run in runs]

    iteration_counts = dict(
        (
            await db.execute(
                select(RunIteration.run_id, func.count()).where(RunIteration.run_id.in_(run_ids)).group_by(RunIteration.run_id)
            )
        ).all()
    )
    token_sums = dict(
        (
            await db.execute(
                select(AgentExecution.run_id, func.coalesce(func.sum(LLMExecution.total_tokens), 0))
                .join(AgentExecution, LLMExecution.agent_execution_id == AgentExecution.id)
                .where(AgentExecution.run_id.in_(run_ids))
                .group_by(AgentExecution.run_id)
            )
        ).all()
    )
    latest_decisions: dict[uuid.UUID, Decision] = {}
    for decision in (
        await db.execute(select(Decision).where(Decision.run_id.in_(run_ids)).order_by(Decision.created_at))
    ).scalars():
        latest_decisions[decision.run_id] = decision  # ascending order: the last write is the newest

    return [
        run_row(
            run, iterations=iteration_counts.get(run.id, 0), tokens=int(token_sums.get(run.id, 0)),
            decision=latest_decisions.get(run.id),
        )
        for run in runs
    ]

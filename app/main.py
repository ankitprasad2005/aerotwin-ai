from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent_executions import router as agent_executions_router
from app.api.datasets import router as datasets_router
from app.api.decision_weights import router as decision_weights_router
from app.api.decisions import router as decisions_router
from app.api.events import router as events_router
from app.api.evidence import router as evidence_router
from app.api.llm_executions import router as llm_executions_router
from app.api.runs import router as runs_router
from app.api.stats import router as stats_router
from app.api.tool_executions import router as tool_executions_router
from app.api.web_search import router as web_search_router
from app.api.websocket import router as websocket_router
from app.config import get_settings
from app.db import async_session_factory
from app.models import digital_twin, external, observability  # noqa: F401  (register tables on Base.metadata)
from app.seed.seed import run_seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    # NOTE: safe to run on every startup because run_seed() no-ops once Airport
    # rows exist, and Airport shares no FK/relationship with OrchestrationRun or
    # any observability table — real run history is never touched by reseeding.
    # Not safe for concurrent multi-replica startup (Phase 1 is single-instance).
    async with async_session_factory() as session:
        await run_seed(session)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AeroTwin AI", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        # No auth/cookies in Phase 1, so no credentialed cross-origin requests are
        # needed. Keep False until an auth mechanism actually requires it, so the
        # choice to allow credentials is deliberate rather than inherited.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (
        runs_router,
        evidence_router,
        datasets_router,
        web_search_router,
        decision_weights_router,
        stats_router,
        agent_executions_router,
        llm_executions_router,
        tool_executions_router,
        decisions_router,
        events_router,
        websocket_router,
    ):
        app.include_router(router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()

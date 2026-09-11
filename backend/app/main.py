from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent_executions import router as agent_executions_router
from app.api.decisions import router as decisions_router
from app.api.events import router as events_router
from app.api.llm_executions import router as llm_executions_router
from app.api.runs import router as runs_router
from app.api.tool_executions import router as tool_executions_router
from app.api.websocket import router as websocket_router
from app.config import get_settings
from app.db import async_session_factory
from app.seed.seed import run_seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session_factory() as session:
        await run_seed(session)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AeroTwin AI", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (
        runs_router,
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

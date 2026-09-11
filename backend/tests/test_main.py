async def test_lifespan_calls_run_seed_on_startup(monkeypatch):
    import app.main as main_module

    calls = []

    class _FakeSessionCtx:
        async def __aenter__(self):
            return "fake-session"

        async def __aexit__(self, *exc):
            return False

    async def _fake_run_seed(session):
        calls.append(session)

    monkeypatch.setattr(main_module, "async_session_factory", lambda: _FakeSessionCtx())
    monkeypatch.setattr(main_module, "run_seed", _fake_run_seed)

    app = main_module.create_app()
    async with main_module.lifespan(app):
        pass

    assert calls == ["fake-session"]


def test_health_endpoint_returns_ok():
    from starlette.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def _collect_route_paths(routes):
    """Flatten a FastAPI/Starlette route list into a set of registered paths.

    fastapi>=0.14x wraps routers added via ``include_router()`` in a lazy
    ``_IncludedRouter`` object (instead of eagerly flattening sub-routes into
    ``app.routes`` like older versions did), so plain routes and included
    routers must be handled separately here.
    """
    paths = set()
    for route in routes:
        path = getattr(route, "path", None)
        if path is not None:
            paths.add(path)
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            paths |= _collect_route_paths(original_router.routes)
    return paths


def test_create_app_registers_all_expected_routes():
    from app.main import create_app

    app = create_app()
    paths = _collect_route_paths(app.routes)

    assert "/api/runs" in paths
    assert "/api/runs/{run_id}" in paths
    assert "/api/runs/{run_id}/graph" in paths
    assert "/api/agent-executions/{agent_execution_id}" in paths
    assert "/api/llm-executions/{llm_execution_id}" in paths
    assert "/api/tool-executions/{tool_execution_id}" in paths
    assert "/api/decisions/{decision_id}" in paths
    assert "/api/events" in paths
    assert "/ws/events" in paths
    assert "/api/health" in paths


def test_health_endpoint_never_exposes_openai_api_key(monkeypatch):
    from starlette.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("AEROTWIN_OPENAI_API_KEY", "sk-super-secret-value")
    get_settings.cache_clear()

    client = TestClient(create_app())
    response = client.get("/api/health")

    assert "sk-super-secret-value" not in response.text
    get_settings.cache_clear()

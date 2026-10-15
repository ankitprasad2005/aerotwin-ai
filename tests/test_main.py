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


def _cors_preflight(origin: str):
    from starlette.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    return client.options(
        "/api/runs",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_cors_allows_a_private_lan_origin_by_default():
    """The UI is regularly opened from another device or container on the same network, where the
    browser's origin is the host's LAN IP rather than localhost; rejecting it broke every request."""
    response = _cors_preflight("http://192.168.68.179:3005")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://192.168.68.179:3005"


def test_cors_allows_the_configured_localhost_origin():
    response = _cors_preflight("http://localhost:5173")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_a_public_internet_origin():
    response = _cors_preflight("https://evil.example.com")

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_new_api_routers_are_registered_with_their_prefixes():
    from app.api import datasets, decision_weights, stats, web_search
    from app.main import create_app

    assert datasets.router.prefix == "/api/datasets"
    assert web_search.router.prefix == "/api/web-search"
    assert decision_weights.router.prefix == "/api/decision-weights"
    assert stats.router.prefix == "/api/stats"
    paths = set(create_app().openapi()["paths"])
    assert "/api/runs/{run_id}/evidence" in paths

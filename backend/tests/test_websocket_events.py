from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.deps import get_bus
from app.api.websocket import router as websocket_router
from app.events.bus import EventBus


def _build_app():
    app = FastAPI()
    app.include_router(websocket_router)
    bus = EventBus()
    app.dependency_overrides[get_bus] = lambda: bus

    @app.post("/test/publish")
    async def _publish(payload: dict):
        await bus.publish(payload)
        return {"ok": True}

    return app, bus


def test_websocket_receives_broadcast_event():
    app, bus = _build_app()
    client = TestClient(app)

    with client.websocket_connect("/ws/events") as websocket:
        client.post("/test/publish", json={"event_type": "agent.started", "payload": {"agent_type": "NETWORK"}})
        message = websocket.receive_json()

    assert message["event_type"] == "agent.started"
    assert message["payload"] == {"agent_type": "NETWORK"}


def test_websocket_receives_multiple_events_in_order():
    app, bus = _build_app()
    client = TestClient(app)

    with client.websocket_connect("/ws/events") as websocket:
        client.post("/test/publish", json={"event_type": "agent.started"})
        client.post("/test/publish", json={"event_type": "agent.completed"})
        first = websocket.receive_json()
        second = websocket.receive_json()

    assert [first["event_type"], second["event_type"]] == ["agent.started", "agent.completed"]


def test_websocket_disconnect_unsubscribes():
    app, bus = _build_app()
    client = TestClient(app)

    with client.websocket_connect("/ws/events"):
        assert len(bus._subscribers) == 1

    assert len(bus._subscribers) == 0

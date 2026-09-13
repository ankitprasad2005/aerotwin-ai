import asyncio

from fastapi import FastAPI, WebSocketDisconnect
from starlette.testclient import TestClient

from app.api.deps import get_bus
from app.api.websocket import router as websocket_router, websocket_events
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


class _FakeWebSocket:
    """Stand-in transport that lets us deterministically trigger the
    WebSocketDisconnect-during-send path, which is not reliably reproducible
    through starlette's TestClient (the real disconnect timing races the
    server-side send). accept()/send_json() mirror the real WebSocket's
    signatures; send_json raises WebSocketDisconnect on its second call to
    simulate the client vanishing mid-broadcast.
    """

    def __init__(self):
        self.accepted = False
        self.sent: list[dict] = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, message: dict):
        self.sent.append(message)
        if len(self.sent) >= 2:
            raise WebSocketDisconnect()


async def test_websocket_events_swallows_disconnect_and_unsubscribes():
    """When the client disconnects while a message is being sent, the handler's
    `except WebSocketDisconnect: pass` must swallow the error (not propagate it)
    and the `finally` must still unsubscribe the queue from the bus."""
    bus = EventBus()
    queue: asyncio.Queue = asyncio.Queue()
    bus._subscribers.add(queue)
    original_subscribe = bus.subscribe
    bus.subscribe = lambda: queue  # force websocket_events onto our pre-wired queue

    await queue.put({"event_type": "agent.started"})
    await queue.put({"event_type": "agent.completed"})

    ws = _FakeWebSocket()

    await websocket_events(ws, bus)  # must return normally, not raise

    assert ws.accepted is True
    assert ws.sent == [{"event_type": "agent.started"}, {"event_type": "agent.completed"}]
    assert queue not in bus._subscribers

    bus.subscribe = original_subscribe

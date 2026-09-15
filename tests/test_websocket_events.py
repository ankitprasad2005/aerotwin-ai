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
    server-side send). accept()/send_json()/receive() mirror the real WebSocket's
    signatures; send_json raises WebSocketDisconnect on its second call to
    simulate the client vanishing mid-broadcast.

    `incoming` scripts what receive() returns, in order; once exhausted, receive()
    blocks forever, like a connected client that never sends anything.
    """

    def __init__(self, incoming: list[dict] | None = None, send_error: Exception | None = None):
        self.accepted = False
        self.sent: list[dict] = []
        self._incoming = list(incoming or [])
        self._send_error = send_error

    async def accept(self):
        self.accepted = True

    async def send_json(self, message: dict):
        if self._send_error is not None:
            raise self._send_error
        self.sent.append(message)
        if len(self.sent) >= 2:
            raise WebSocketDisconnect()

    async def receive(self):
        if self._incoming:
            return self._incoming.pop(0)
        await asyncio.Event().wait()


def _bus_with_queue():
    bus = EventBus()
    queue: asyncio.Queue = asyncio.Queue()
    bus._subscribers.add(queue)
    bus.subscribe = lambda: queue  # force websocket_events onto our pre-wired queue
    return bus, queue


async def test_websocket_events_swallows_disconnect_and_unsubscribes():
    """When the client disconnects while a message is being sent, the handler
    must swallow the WebSocketDisconnect (not propagate it) and still unsubscribe
    the queue from the bus."""
    bus, queue = _bus_with_queue()

    await queue.put({"event_type": "agent.started"})
    await queue.put({"event_type": "agent.completed"})

    ws = _FakeWebSocket()

    await websocket_events(ws, bus)  # must return normally, not raise

    assert ws.accepted is True
    assert ws.sent == [{"event_type": "agent.started"}, {"event_type": "agent.completed"}]
    assert queue not in bus._subscribers


async def test_websocket_events_notices_idle_client_disconnect_and_unsubscribes():
    """A client that disconnects while no events are flowing must be noticed via
    receive() — not only on the next send — so the handler returns and the
    subscriber queue doesn't leak. Messages the client sends are ignored."""
    bus, queue = _bus_with_queue()
    ws = _FakeWebSocket(incoming=[{"type": "websocket.receive", "text": "ping"}, {"type": "websocket.disconnect"}])

    await asyncio.wait_for(websocket_events(ws, bus), timeout=1)

    assert ws.sent == []
    assert queue not in bus._subscribers


async def test_websocket_events_propagates_unexpected_send_errors_and_unsubscribes():
    import pytest

    bus, queue = _bus_with_queue()
    await queue.put({"event_type": "agent.started"})
    ws = _FakeWebSocket(send_error=RuntimeError("serialization blew up"))

    with pytest.raises(RuntimeError):
        await asyncio.wait_for(websocket_events(ws, bus), timeout=1)

    assert queue not in bus._subscribers

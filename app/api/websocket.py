import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import get_bus
from app.events.bus import EventBus

router = APIRouter()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket, bus: EventBus = Depends(get_bus)):
    await websocket.accept()
    queue = bus.subscribe()

    async def forward_events() -> None:
        while True:
            message = await queue.get()
            await websocket.send_json(message)

    async def wait_for_disconnect() -> None:
        # Clients never send anything meaningful, but receive() is the only way to
        # notice a disconnect while no events are flowing. Without it, the handler
        # would sit in queue.get() indefinitely after the client left — leaking the
        # subscriber queue and blocking server shutdown until the next event arrived.
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return

    tasks = {asyncio.create_task(forward_events()), asyncio.create_task(wait_for_disconnect())}
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                raise exc
    finally:
        for task in tasks:
            task.cancel()
        bus.unsubscribe(queue)

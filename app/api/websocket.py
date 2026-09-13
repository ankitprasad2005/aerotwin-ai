from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import get_bus
from app.events.bus import EventBus

router = APIRouter()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket, bus: EventBus = Depends(get_bus)):
    await websocket.accept()
    queue = bus.subscribe()
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
from core.assistant import bytex_core
from models.schemas import WSEvent
from monitoring.service import live_system_monitor
from monitoring.models import SystemEvent

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        init_event = WSEvent(type="STATE_CHANGE", state="idle", message="ByteX WebSocket Connected")
        await websocket.send_text(init_event.model_dump_json())

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_event(self, websocket: WebSocket, event: WSEvent):
        from core.response_sanitizer import ResponseSanitizer
        if event.type in ["ASSISTANT_COMPLETE", "ASSISTANT_MESSAGE"] and event.message:
            event.message = ResponseSanitizer.sanitize(event.message)
        elif event.type == "ASSISTANT_DELTA":
            delta_str = ""
            if event.content:
                delta_str = str(event.content)
            elif event.message:
                delta_str = str(event.message)
            elif event.data and isinstance(event.data, dict) and "delta" in event.data:
                delta_str = str(event.data.get("delta", ""))

            if delta_str and any(p in delta_str for p in ["<think>", "</think>", "<tool>", "</tool>", "<tool_call>", "</tool_call>", '"tool_use"', '"thought"']):
                return
        await websocket.send_text(event.model_dump_json())

    async def broadcast(self, event_dict: dict):
        """Broadcasts structured events to all connected frontend clients."""
        text = json.dumps(event_dict)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(text)
            except Exception:
                pass

manager = ConnectionManager()

# Hook Live System Monitor events to WebSocket broadcast
async def broadcast_system_event(event: SystemEvent):
    payload = {
        "type": "SYSTEM_NOTIFICATION",
        "data": event.to_dict(),
        "message": event.message,
    }
    await manager.broadcast(payload)

live_system_monitor.add_event_listener(broadcast_system_event)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                user_msg = payload.get("message") or payload.get("content") or payload.get("data")
                
                if user_msg:
                    # Stream real-time events (ASSISTANT_DELTA, ASSISTANT_COMPLETE, STATE_CHANGE)
                    async for event in bytex_core.process_user_message(str(user_msg)):
                        await manager.send_event(websocket, event)
                else:
                    err_event = WSEvent(type="ERROR", message="Invalid payload: 'message' required", state="error")
                    await manager.send_event(websocket, err_event)

            except json.JSONDecodeError:
                err_event = WSEvent(type="ERROR", message="Invalid JSON format", state="error")
                await manager.send_event(websocket, err_event)

    except WebSocketDisconnect:
        manager.disconnect(websocket)

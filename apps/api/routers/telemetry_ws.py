"""
FaceSentry Real-Time Telemetry State Broker & WebSocket Router
Manages live localhost WebSocket streaming to the Next.js Dashboard.
"""

import time
import json
import logging
import asyncio
from typing import Set, Optional, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.responses import JSONResponse

from packages.shared.schemas import (
    TelemetrySnapshot,
    WebSocketMessage,
    TelemetryPublishRequest,
)

logger = logging.getLogger("facesentry.api.telemetry")
router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


class TelemetryBroker:
    """
    In-process state broker maintaining the latest operational snapshot
    and broadcasting real-time updates to connected dashboard clients.
    """

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._latest_snapshot: Optional[TelemetrySnapshot] = None
        self._lock = asyncio.Lock()

    @property
    def active_connections_count(self) -> int:
        return len(self._connections)

    def get_latest_snapshot(self) -> Optional[TelemetrySnapshot]:
        return self._latest_snapshot

    async def connect(self, websocket: WebSocket) -> None:
        """Register a new WebSocket client and send initial state snapshot."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
            logger.info(f"Dashboard WebSocket client connected (Total: {len(self._connections)})")

        # Immediately send current state if available
        if self._latest_snapshot:
            init_msg = WebSocketMessage(
                type="SNAPSHOT",
                timestamp=self._latest_snapshot.timestamp,
                schema_version="1.0",
                payload=self._latest_snapshot.model_dump(),
            )
            try:
                await websocket.send_text(init_msg.model_dump_json())
            except Exception as exc:
                logger.warning(f"Failed to send initial snapshot to new client: {exc}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a disconnected WebSocket client."""
        async with self._lock:
            self._connections.discard(websocket)
            logger.info(f"Dashboard WebSocket client disconnected (Remaining: {len(self._connections)})")

    async def broadcast_message(self, message: WebSocketMessage) -> None:
        """Broadcast a message envelope to all active subscribers."""
        if not self._connections:
            return

        payload_json = message.model_dump_json()
        dead_connections: Set[WebSocket] = set()

        async with self._lock:
            for ws in list(self._connections):
                try:
                    await ws.send_text(payload_json)
                except Exception as exc:
                    logger.debug(f"Error sending message to client: {exc}")
                    dead_connections.add(ws)

            # Prune closed connections
            for dead_ws in dead_connections:
                self._connections.discard(dead_ws)

    async def update_snapshot(self, snapshot: TelemetrySnapshot) -> None:
        """Update current snapshot and broadcast to clients."""
        self._latest_snapshot = snapshot
        msg = WebSocketMessage(
            type="SNAPSHOT",
            timestamp=snapshot.timestamp,
            schema_version="1.0",
            payload=snapshot.model_dump(),
        )
        await self.broadcast_message(msg)

    async def emit_security_event(self, event_data: Dict[str, Any]) -> None:
        """Broadcast an immediate security event."""
        now = time.time()
        msg = WebSocketMessage(
            type="SECURITY_EVENT",
            timestamp=now,
            schema_version="1.0",
            payload=event_data,
        )
        await self.broadcast_message(msg)


# Global in-process broker singleton
telemetry_broker = TelemetryBroker()


@router.websocket("/ws")
async def telemetry_websocket_endpoint(websocket: WebSocket):
    """
    Localhost-only real-time telemetry WebSocket endpoint for FaceSentry Dashboard.
    Provides sub-second status telemetry and immediate transition security events.
    """
    # Verify client is localhost (or in-memory testclient)
    client_host = websocket.client.host if websocket.client else "unknown"
    if client_host not in ["127.0.0.1", "localhost", "::1", "testclient"]:
        logger.warning(f"Rejected non-localhost WebSocket connection attempt from: {client_host}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await telemetry_broker.connect(websocket)
    try:
        while True:
            # Listen for client heartbeat/ping messages
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
                msg_type = msg.get("type", "").upper()

                if msg_type == "PING":
                    pong = WebSocketMessage(
                        type="PONG",
                        timestamp=time.time(),
                        schema_version="1.0",
                        payload={"reply_to": "PING"},
                    )
                    await websocket.send_text(pong.model_dump_json())
            except json.JSONDecodeError:
                logger.debug(f"Ignored non-JSON text from WebSocket client: {data_text[:50]}")
    except WebSocketDisconnect:
        await telemetry_broker.disconnect(websocket)
    except Exception as exc:
        logger.debug(f"WebSocket session terminated: {exc}")
        await telemetry_broker.disconnect(websocket)


@router.post("/publish")
async def publish_telemetry(req: TelemetryPublishRequest):
    """
    Internal agent publishing endpoint.
    Receives snapshots or transition security events and broadcasts via WebSocket.
    """
    if req.snapshot:
        await telemetry_broker.update_snapshot(req.snapshot)
    
    if req.event:
        await telemetry_broker.emit_security_event(req.event)

    return {
        "status": "ok",
        "clients_notified": telemetry_broker.active_connections_count,
        "timestamp": time.time(),
    }


@router.get("/snapshot")
async def get_current_snapshot():
    """Retrieve the latest operational telemetry snapshot via REST."""
    snapshot = telemetry_broker.get_latest_snapshot()
    if not snapshot:
        return JSONResponse(
            status_code=200,
            content={"status": "NO_SNAPSHOT_AVAILABLE", "message": "Agent has not published telemetry yet."},
        )
    return snapshot

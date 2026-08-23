"""
Unit & Integration Tests for FaceSentry Real-Time Telemetry WebSocket & State Broker
"""

import time
import json
import pytest
from starlette.testclient import TestClient

from apps.api.main import app
from apps.api.routers.telemetry_ws import telemetry_broker
from packages.shared.schemas import TelemetrySnapshot, TelemetryPublishRequest


@pytest.fixture
def client():
    return TestClient(app)


def test_telemetry_snapshot_rest_endpoint(client):
    """Verify REST snapshot endpoint returns valid JSON."""
    res = client.get("/api/v1/telemetry/snapshot")
    assert res.status_code == 200
    assert "status" in res.json() or "timestamp" in res.json()


def test_telemetry_publish_and_snapshot_retrieval(client):
    """Verify publishing snapshot via REST updates the in-process broker."""
    snapshot = TelemetrySnapshot(
        timestamp=time.time(),
        agent_status="RUNNING",
        camera_status="CONNECTED",
        authentication_state="AUTHENTICATED",
        recognition_similarity=0.92,
        liveness_state="VERIFIED",
        liveness_verified=True,
        liveness_confidence=0.98,
        face_detected=True,
        face_count=1,
        absence_duration=0.0,
        stranger_duration=0.0,
        spoof_duration=0.0,
        decision_state="AUTHENTICATED_PRESENT",
        lock_requested=False,
        system_uptime=123.4,
    )

    req = TelemetryPublishRequest(snapshot=snapshot, message_type="SNAPSHOT")
    post_res = client.post("/api/v1/telemetry/publish", json=req.model_dump())
    assert post_res.status_code == 200
    assert post_res.json()["status"] == "ok"

    # Verify latest snapshot via REST
    get_res = client.get("/api/v1/telemetry/snapshot")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["authentication_state"] == "AUTHENTICATED"
    assert data["recognition_similarity"] == 0.92
    assert data["decision_state"] == "AUTHENTICATED_PRESENT"


def test_websocket_connect_receives_initial_snapshot(client):
    """Verify newly connected WebSocket receives the current state snapshot immediately."""
    # Ensure a snapshot exists in broker
    snapshot = TelemetrySnapshot(
        timestamp=1000.0,
        agent_status="RUNNING",
        camera_status="CONNECTED",
        authentication_state="AUTHENTICATED",
        recognition_similarity=0.88,
        liveness_state="VERIFIED",
        liveness_verified=True,
        liveness_confidence=0.95,
        face_detected=True,
        face_count=1,
        absence_duration=0.0,
        stranger_duration=0.0,
        spoof_duration=0.0,
        decision_state="AUTHENTICATED_PRESENT",
        lock_requested=False,
        system_uptime=50.0,
    )
    req = TelemetryPublishRequest(snapshot=snapshot, message_type="SNAPSHOT")
    client.post("/api/v1/telemetry/publish", json=req.model_dump())

    # Connect WebSocket
    with client.websocket_connect("/api/v1/telemetry/ws") as websocket:
        data_text = websocket.receive_text()
        msg = json.loads(data_text)
        assert msg["type"] == "SNAPSHOT"
        assert msg["payload"]["authentication_state"] == "AUTHENTICATED"
        assert msg["payload"]["recognition_similarity"] == 0.88


def test_websocket_ping_pong_heartbeat(client):
    """Verify client PING returns server PONG message."""
    with client.websocket_connect("/api/v1/telemetry/ws") as websocket:
        # Drain initial snapshot if present
        if telemetry_broker.get_latest_snapshot():
            websocket.receive_text()

        # Send PING
        websocket.send_text(json.dumps({"type": "PING"}))
        response_text = websocket.receive_text()
        msg = json.loads(response_text)
        assert msg["type"] == "PONG"
        assert msg["payload"]["reply_to"] == "PING"


def test_websocket_broadcast_live_security_event(client):
    """Verify security event published to API is broadcast live to connected WebSockets."""
    with client.websocket_connect("/api/v1/telemetry/ws") as websocket:
        # Drain initial snapshot if present
        if telemetry_broker.get_latest_snapshot():
            websocket.receive_text()

        # Publish security event
        event_payload = {
            "event_type": "ABSENCE_STARTED",
            "reason": "No face detected in ROI",
            "timestamp": time.time(),
        }
        req = TelemetryPublishRequest(event=event_payload, message_type="SECURITY_EVENT")
        client.post("/api/v1/telemetry/publish", json=req.model_dump())

        # Receive broadcast over WebSocket
        msg_text = websocket.receive_text()
        msg = json.loads(msg_text)
        assert msg["type"] == "SECURITY_EVENT"
        assert msg["payload"]["event_type"] == "ABSENCE_STARTED"
        assert msg["payload"]["reason"] == "No face detected in ROI"

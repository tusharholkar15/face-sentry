"""
Unit and Integration Tests for FaceSentry Enrollment API Router
"""

import json
import pytest
from starlette.testclient import TestClient
from apps.api.main import app
from apps.api.routers.enroll_routes import enrollment_state


@pytest.fixture(autouse=True)
def reset_enrollment_state():
    enrollment_state.reset()
    yield
    enrollment_state.reset()


@pytest.fixture
def client():
    return TestClient(app)


def test_enrollment_initial_status(client):
    """Verify initial enrollment status is IDLE."""
    res = client.get("/api/v1/enrollment/status")
    assert res.status_code == 200
    data = res.json()
    assert data["state"] == "IDLE"
    assert data["progress"] == 0.0
    assert data["captured_samples"] == 0
    assert data["is_complete"] is False


def test_enrollment_start(client):
    """Verify starting an enrollment session initializes state and target samples."""
    payload = {"user_id": "test_user", "target_samples": 10}
    res = client.post("/api/v1/enrollment/start", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["state"] == "CAPTURING"
    assert data["required_samples"] == 10
    assert data["guidance"] == "LOOK_FORWARD"


def test_enrollment_cancel(client):
    """Verify cancelling an active enrollment transitions to CANCELLED."""
    client.post("/api/v1/enrollment/start", json={"user_id": "test_user", "target_samples": 10})
    res = client.post("/api/v1/enrollment/cancel")
    assert res.status_code == 200
    data = res.json()
    assert data["state"] == "CANCELLED"
    assert data["error_message"] is not None


def test_enrollment_finalize_invalid_transition(client):
    """Verify finalizing before capturing samples returns 400 Bad Request."""
    res = client.post("/api/v1/enrollment/finalize")
    assert res.status_code == 400
    assert "Cannot finalize" in res.json()["detail"]


def test_enrollment_finalize_success_flow(client):
    """Verify finalize succeeds when profile is successfully persisted and valid."""
    from packages.shared.constants import DEFAULT_ENROLLMENT_DIR
    from apps.agent.facesentry_agent.biometric_storage import BiometricStorage
    import numpy as np
    import os
    
    storage = BiometricStorage(DEFAULT_ENROLLMENT_DIR)
    
    np.random.seed(42)
    embedding = np.random.randn(128).astype(np.float32)
    embedding /= np.linalg.norm(embedding)
    
    storage.save_profile(
        profile_name="test_user",
        reference_embedding=embedding,
        sample_count=10,
        quality_metrics={"sample_count": 10, "avg_confidence": 0.95}
    )
    
    try:
        client.post("/api/v1/enrollment/start", json={"user_id": "test_user", "target_samples": 10})
        res = client.post("/api/v1/enrollment/finalize")
        assert res.status_code == 200
        data = res.json()
        assert data["state"] == "COMPLETED"
        assert data["progress"] == 1.0
        assert data["is_complete"] is True
    finally:
        profile_path = os.path.join(DEFAULT_ENROLLMENT_DIR, "test_user.dat")
        if os.path.exists(profile_path):
            os.remove(profile_path)


def test_enrollment_finalize_persistence_failure(client):
    """Verify finalize fails and returns 400 Bad Request when profile file is missing."""
    client.post("/api/v1/enrollment/start", json={"user_id": "missing_user", "target_samples": 10})
    res = client.post("/api/v1/enrollment/finalize")
    assert res.status_code == 400
    assert "ENROLLMENT_STORAGE_FAILED" in res.json()["detail"]


def test_enrollment_api_privacy_boundaries(client):
    """Verify API responses strictly omit raw embeddings, crops, landmarks, or DPAPI ciphertext."""
    client.post("/api/v1/enrollment/start", json={"user_id": "test_user", "target_samples": 10})
    res = client.get("/api/v1/enrollment/status")
    assert res.status_code == 200
    raw_json = json.dumps(res.json()).lower()

    forbidden_terms = ["embedding", "landmark", "crop", "vector", "ciphertext", "dpapi", "pin"]
    for term in forbidden_terms:
        assert term not in raw_json


def test_enrollment_update_progress_and_websocket_broadcast(client):
    """Verify internal agent progress updates broadcast to connected WebSockets."""
    with client.websocket_connect("/api/v1/telemetry/ws") as ws:
        # Send update from agent
        update_payload = {
            "status": {
                "state": "CAPTURING",
                "progress": 0.5,
                "captured_samples": 5,
                "required_samples": 10,
                "quality": "GOOD",
                "guidance": "GOOD_SAMPLE",
                "liveness_verified": False,
                "error_message": None,
                "is_complete": False,
            }
        }
        post_res = client.post("/api/v1/enrollment/update_progress", json=update_payload)
        assert post_res.status_code == 200

        # Receive WebSocket message
        msg_text = ws.receive_text()
        msg = json.loads(msg_text)
        assert msg["type"] == "ENROLLMENT_PROGRESS"
        assert msg["payload"]["captured_samples"] == 5
        assert msg["payload"]["guidance"] == "GOOD_SAMPLE"

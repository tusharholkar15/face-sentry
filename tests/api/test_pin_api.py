"""
Unit and Integration Tests for FaceSentry PIN API Router
"""

import json
import pytest
from starlette.testclient import TestClient
from apps.api.main import app
from apps.api.routers.pin_routes import pin_service


@pytest.fixture(autouse=True)
def clean_pin_storage(tmp_path):
    temp_file = str(tmp_path / "test_pin_credentials.json")
    pin_service.storage_file = tmp_path / "test_pin_credentials.json"
    pin_service._failed_attempts = 0
    pin_service._locked_until = None
    pin_service._recovery_until = None
    yield
    if pin_service.storage_file.exists():
        pin_service.storage_file.unlink()


@pytest.fixture
def client():
    return TestClient(app)


def test_pin_api_status_initial(client):
    """Verify initial PIN status returns not configured."""
    res = client.get("/api/v1/pin/status")
    assert res.status_code == 200
    data = res.json()
    assert data["is_configured"] is False
    assert data["is_locked"] is False
    assert data["attempts_remaining"] == 5


def test_pin_api_setup_and_verify(client):
    """Verify full setup, verification, and recovery workflow over API."""
    setup_payload = {"new_pin": "1234", "confirm_pin": "1234"}
    setup_res = client.post("/api/v1/pin/setup", json=setup_payload)
    assert setup_res.status_code == 200
    assert setup_res.json()["is_configured"] is True

    # Verify correct PIN
    verify_payload = {"pin": "1234"}
    verify_res = client.post("/api/v1/pin/verify", json=verify_payload)
    assert verify_res.status_code == 200
    data = verify_res.json()
    assert data["authenticated"] is True
    assert data["in_recovery"] is True
    assert data["recovery_until"] is not None


def test_pin_api_incorrect_pin_and_lockout(client):
    """Verify failed attempts and lockout responses."""
    client.post("/api/v1/pin/setup", json={"new_pin": "9876", "confirm_pin": "9876"})

    # Submit 4 wrong attempts
    for _ in range(4):
        res = client.post("/api/v1/pin/verify", json={"pin": "0000"})
        assert res.status_code == 200
        assert res.json()["authenticated"] is False
        assert res.json()["is_locked"] is False

    # 5th wrong attempt triggers lockout
    res_lock = client.post("/api/v1/pin/verify", json={"pin": "0000"})
    assert res_lock.status_code == 200
    assert res_lock.json()["authenticated"] is False
    assert res_lock.json()["is_locked"] is True
    assert res_lock.json()["locked_until"] is not None


def test_pin_api_change_flow(client):
    """Verify change PIN endpoint works and old PIN is invalidated."""
    client.post("/api/v1/pin/setup", json={"new_pin": "1111", "confirm_pin": "1111"})

    change_payload = {
        "current_pin": "1111",
        "new_pin": "2222",
        "confirm_pin": "2222",
    }
    change_res = client.post("/api/v1/pin/change", json=change_payload)
    assert change_res.status_code == 200

    # Old PIN fails
    res_old = client.post("/api/v1/pin/verify", json={"pin": "1111"})
    assert res_old.json()["authenticated"] is False

    # New PIN succeeds
    res_new = client.post("/api/v1/pin/verify", json={"pin": "2222"})
    assert res_new.json()["authenticated"] is True


def test_pin_api_privacy_boundaries(client):
    """Verify PIN API responses never leak password hashes, salts, or candidate PINs."""
    client.post("/api/v1/pin/setup", json={"new_pin": "5555", "confirm_pin": "5555"})
    res = client.get("/api/v1/pin/status")
    assert res.status_code == 200
    raw_text = json.dumps(res.json()).lower()

    forbidden = ["salt", "hash", "5555", "secret", "password", "key"]
    for term in forbidden:
        assert term not in raw_text

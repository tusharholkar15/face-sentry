"""
Tests for Status, Config, and Event Endpoints
"""


def test_get_status_endpoint(client):
    """Verify GET /api/v1/status returns default system status."""
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["state"] in ["UNINITIALIZED", "IDLE"]
    assert "profile_enrolled" in data
    assert "uptime_seconds" in data


def test_get_and_patch_config(client):
    """Verify reading and updating configuration parameters."""
    # 1. Get default config
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    config_data = response.json()
    assert "hardware" in config_data
    assert "policies" in config_data
    assert config_data["policies"]["absence_timeout_seconds"] == 10

    # 2. Modify config
    config_data["policies"]["absence_timeout_seconds"] = 15
    config_data["policies"]["similarity_threshold"] = 0.70

    patch_res = client.patch("/api/v1/config", json=config_data)
    assert patch_res.status_code == 200
    updated_data = patch_res.json()
    assert updated_data["policies"]["absence_timeout_seconds"] == 15
    assert updated_data["policies"]["similarity_threshold"] == 0.70

    # 3. Verify changes persisted
    get_res2 = client.get("/api/v1/config")
    assert get_res2.status_code == 200
    assert get_res2.json()["policies"]["absence_timeout_seconds"] == 15


def test_events_endpoint(client):
    """Verify security event recording and querying."""
    # Fetch initial events
    res = client.get("/api/v1/events")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # Post an event
    payload = {
        "event_type": "PIN_VERIFIED",
        "action_taken": "ALLOW_DASHBOARD_ACCESS",
        "confidence": 1.0,
        "metadata": {"actor": "local_user"},
    }
    create_res = client.post("/api/v1/events", json=payload)
    assert create_res.status_code == 201
    created_event = create_res.json()
    assert created_event["event_type"] == "PIN_VERIFIED"
    assert created_event["action_taken"] == "ALLOW_DASHBOARD_ACCESS"

"""
API Configuration tests for Browser Protection settings
"""

import pytest

def test_browser_protection_config_roundtrip(client):
    # Get current config
    res_get = client.get("/api/v1/config")
    assert res_get.status_code == 200
    config = res_get.json()

    # Verify defaults
    assert "browser_protection" in config
    assert config["browser_protection"]["enabled"] is False
    assert config["browser_protection"]["mode"] == "DISABLED"

    # Patch config
    config["browser_protection"]["enabled"] = True
    config["browser_protection"]["mode"] = "CLOSE_BROWSER_AND_CLEAR_SESSION_COOKIES"
    config["browser_protection"]["close_timeout_seconds"] = 10.0

    res_patch = client.patch("/api/v1/config", json=config)
    assert res_patch.status_code == 200
    patched_config = res_patch.json()

    # Verify updated values
    assert patched_config["browser_protection"]["enabled"] is True
    assert patched_config["browser_protection"]["mode"] == "CLOSE_BROWSER_AND_CLEAR_SESSION_COOKIES"
    assert patched_config["browser_protection"]["close_timeout_seconds"] == 10.0

    # Clean up (restore defaults)
    config["browser_protection"]["enabled"] = False
    config["browser_protection"]["mode"] = "DISABLED"
    client.patch("/api/v1/config", json=config)

"""
Tests for API Health Check Endpoints
"""


def test_root_health_endpoint(client):
    """Verify GET /health returns 200 OK and expected service metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["service"] == "facesentry-api"
    assert "version" in data
    assert "timestamp" in data
    assert "database" in data


def test_versioned_health_endpoint(client):
    """Verify GET /api/v1/health returns 200 OK and matches root health format."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "facesentry-api"
    assert data["status"] in ["healthy", "degraded"]

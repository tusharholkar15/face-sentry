"""
Global Pytest Configuration and Test Fixtures
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from apps.api.main import create_app
from apps.api.database import db_manager


@pytest.fixture
def tmp_db_path(tmp_path):
    """Provide a temporary SQLite database path for isolated tests."""
    return str(tmp_path / "test_facesentry.db")


@pytest.fixture
def client(tmp_db_path):
    """FastAPI TestClient with isolated temporary database."""
    os.environ["FACESENTRY_DATABASE_PATH"] = tmp_db_path
    db_manager.db_path = tmp_db_path
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

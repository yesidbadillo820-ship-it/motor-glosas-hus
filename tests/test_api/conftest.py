"""
Pytest configuration for API tests.
Includes client fixture for FastAPI test client.
"""
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def client():
    """Provide FastAPI test client."""
    from app.main import app
    return TestClient(app)

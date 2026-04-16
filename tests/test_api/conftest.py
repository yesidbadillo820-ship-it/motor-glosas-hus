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
    """Provide FastAPI test client with lifespan events active.

    Using the context manager triggers the lifespan hook which creates the
    database tables and seeds the admin user before the tests run.
    """
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client

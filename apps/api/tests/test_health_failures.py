import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db
import redis

# Mock a failed DB connection
def override_get_db_failure():
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise Exception("Database connection refused")
        def close(self):
            pass
    yield BrokenSession()

# Mock a failed Redis connection
def override_get_redis_failure():
    raise redis.ConnectionError("Redis connection refused")

@pytest.fixture
def mock_redis_failure(monkeypatch):
    import app.api.health as health_module
    monkeypatch.setattr(health_module, "get_redis_client", override_get_redis_failure)

def test_readiness_db_failure():
    app.dependency_overrides[get_db] = override_get_db_failure
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["status"] == "unavailable"
        assert data["detail"]["dependencies"]["database"] == "down"
    app.dependency_overrides.clear()

def test_readiness_redis_failure(mock_redis_failure):
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["status"] == "unavailable"
        assert data["detail"]["dependencies"]["redis"] == "down"

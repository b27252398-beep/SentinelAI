import pytest
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import SessionLocal

# Models
from app.services.models import Service
from app.telemetry.models import Telemetry
from app.detection.models import DetectorConfig, AnomalyEvent
from app.incidents.models import Incident, IncidentAnomaly
from app.investigations.models import Investigation, Hypothesis
from app.recommendations.models import Recommendation
from app.auth.models import User, Role

# Auth
from app.auth.security import create_access_token, get_password_hash
from app.auth.seed import seed_rbac

# Workers & Services
from app.detection.worker import process_config
from app.incidents.correlation import process_anomaly
from app.investigations.worker import process_investigation
from app.recommendations.worker import generate_recommendation_task

# Main App / API
from fastapi.testclient import TestClient
from app.main import app

class MockRedisLock:
    def __init__(self, key, ex):
        self.key = key
        self.ex = ex
        self._locked = False
    def set(self, value, nx=False, ex=None):
        if not self._locked:
            self._locked = True
            return True
        return False
    def delete(self):
        self._locked = False

class RedisClientMock:
    def lock(self, key, nx, ex):
        return MockRedisLock(key, ex)
    def set(self, key, value, nx=False, ex=None):
        return True
    def delete(self, key):
        pass
    def ping(self):
        return True
    def eval(self, script, numkeys, *keys_and_args):
        return 1

mock_redis_fixture = RedisClientMock()

class MockLLMResponse:
    def __init__(self, hypotheses, recommendation=None):
        self.hypotheses = hypotheses
        self.recommendation = recommendation

class MockProvider:
    model_identifier = "mock-model"
    async def generate_hypotheses(self, prompt, context):
        class MockHypo:
            statement = "Hypo 1"
            reasoning = "Because"
            confidence = 0.9
            is_probable_root_cause = True
            supporting_evidence_ids = []
            contradicting_evidence_ids = []
        return MockLLMResponse([MockHypo()])
    async def generate_recommendations(self, prompt, statement, evidence):
        class MockRec:
            title = "Restart"
            description = "Restart service"
            rationale = "Fix issue"
            recommendation_type = "RESTART"
            expected_effect = "Fixes it"
            risk_level = "LOW"
            confidence = 0.9
            preconditions = []
            validation_steps = []
            rollback_guidance = ""
        return MockLLMResponse([], MockRec())

mock_provider_instance = MockProvider()

@pytest.fixture(autouse=True)
def mock_background_tasks():
    with patch("fastapi.BackgroundTasks.add_task"):
        yield

@pytest.fixture(autouse=True)
def mock_redis():
    with patch("app.db.redis.get_redis_client", return_value=mock_redis_fixture, create=True):
        with patch("redis.Redis", return_value=mock_redis_fixture, create=True):
            with patch("app.investigations.worker.get_llm_provider", return_value=mock_provider_instance):
                with patch("app.recommendations.worker.get_llm_provider", return_value=mock_provider_instance):
                    yield

def create_user_with_role(db: Session, username: str, role_name: str) -> User:
    role = db.query(Role).filter_by(name=role_name).first()
    user = User(
        username=username,
        email=f"{username}@test.com",
        hashed_password=get_password_hash("pass")
    )
    user.roles.append(role)
    db.add(user)
    db.commit()
    return user

def create_auth_headers(user: User):
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_end_to_end_pipeline(client: TestClient, db_session: Session):
    # 0. RBAC Seed
    seed_rbac(db_session)
    admin = create_user_with_role(db_session, "admin", "Administrator")
    engineer = create_user_with_role(db_session, "engineer", "Engineer")
    viewer = create_user_with_role(db_session, "viewer", "Viewer")
    
    admin_headers = create_auth_headers(admin)
    engineer_headers = create_auth_headers(engineer)
    viewer_headers = create_auth_headers(viewer)
    
    # 1. Create a Service
    svc = Service(id=uuid.uuid4(), name=f"DB_{uuid.uuid4().hex[:6]}", environment="prod")
    db_session.add(svc)
    db_session.commit()
    
    # Verify Viewer cannot mutate
    res = client.post("/api/v1/services", json={"name": "TestE2ESvc", "environment": "prod"}, headers=viewer_headers)
    assert res.status_code == 403
    
    # 2. Setup Detection Config
    config = DetectorConfig(
        id=uuid.uuid4(),
        service_id=svc.id,
        detector_type="DB Connection Exhaustion",
        feature="db.connection_count",
        aggregation_function="avg",
        min_raw_samples=1,
        min_baseline_observations=1,
        cooldown_windows=0,
        config={"critical_threshold": 100},
        enabled=True
    )
    db_session.add(config)
    db_session.commit()

    # 3. Ingest Telemetry
    window_end = datetime.now(timezone.utc)
    window_end = window_end.replace(second=0, microsecond=0, minute=(window_end.minute // 5) * 5)
    window_start = window_end - timedelta(minutes=5)

    t1 = Telemetry(
        id=uuid.uuid4(), service_id=svc.id, timestamp=window_start + timedelta(minutes=1),
        telemetry_type="METRIC", fingerprint="fp1", 
        metric_name="db_connections", metric_value=500.0,
        raw_payload="{}"
    )
    db_session.add(t1)
    db_session.commit()
    
    # 4. Run Detection Worker manually
    process_config(db_session, config, window_start, window_end)
    
    anomalies = db_session.query(AnomalyEvent).filter_by(service_id=svc.id).all()
    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly.severity == "P2"
    
    # 5. Run Correlation Worker
    process_anomaly(db_session, anomaly)
    
    incidents = db_session.query(Incident).filter_by(service_id=svc.id).all()
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.status == "Detected"
    assert incident.severity == "P2"
    
    # 6. Start Investigation (Admin)
    res = client.post(f"/api/v1/incidents/{incident.id}/investigations", headers=admin_headers)
    assert res.status_code == 202
    investigation_id = res.json()["id"]
    
    # 7. Process Investigation Worker
    await process_investigation(uuid.UUID(investigation_id), db=db_session)
    
    db_session.refresh(incident)
    inv = db_session.query(Investigation).filter_by(id=uuid.UUID(investigation_id)).first()
    assert inv.status == "complete"
    
    hyps = db_session.query(Hypothesis).filter_by(investigation_id=inv.id).all()
    assert len(hyps) > 0
    probable_rca = [h for h in hyps if h.is_probable_root_cause]
    assert len(probable_rca) == 1
    
    # 8. Generate Recommendation
    res = client.post(f"/api/v1/investigations/{investigation_id}/recommendations", headers=admin_headers)
    assert res.status_code == 202
    
    await generate_recommendation_task(inv.id, db=db_session)
    
    recs = db_session.query(Recommendation).filter_by(investigation_id=inv.id).all()
    assert len(recs) == 1
    rec = recs[0]
    
    # The default LLM mock returns a safe response by default
    assert rec.approval_status in ["PENDING_APPROVAL", "VALIDATION_FAILED"]
    
    if rec.approval_status == "PENDING_APPROVAL":
        # Engineer cannot approve
        res = client.post(f"/api/v1/recommendations/{rec.id}/approve", json={"rationale": "Looks good"}, headers=engineer_headers)
        assert res.status_code == 403
        
        # Admin approves
        res = client.post(f"/api/v1/recommendations/{rec.id}/approve", json={"rationale": "Looks good"}, headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["approval_status"] == "APPROVED"
        
        db_session.refresh(rec)
        assert rec.execution_status == "PENDING"

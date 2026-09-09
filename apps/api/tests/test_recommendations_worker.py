import pytest
from unittest.mock import patch
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.investigations.models import Investigation, Hypothesis
from app.recommendations.models import Recommendation
from app.recommendations.worker import generate_recommendation_task
from app.incidents.models import Incident
from app.services.models import Service

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

mock_redis_fixture = RedisClientMock()

@pytest.fixture(autouse=True)
def mock_redis():
    with patch("app.recommendations.worker.get_redis", return_value=mock_redis_fixture):
        yield

@pytest.mark.asyncio
async def test_worker_success(db_session: Session):
    svc = Service(id=uuid4(), name="TestSvc", environment="prod")
    inc = Incident(id=uuid4(), title="Test", severity="P1", status="Detected", service_id=svc.id, detected_at=datetime.now(timezone.utc), last_anomaly_at=datetime.now(timezone.utc))
    inv = Investigation(id=uuid4(), incident_id=inc.id, status="complete")
    hyp = Hypothesis(id=uuid4(), investigation_id=inv.id, statement="Test statement", reasoning="Test reasoning", confidence=0.9, is_probable_root_cause=True)
    
    db_session.add_all([svc, inc, inv, hyp])
    db_session.commit()
    
    await generate_recommendation_task(inv.id, db=db_session)
    
    recs = db_session.query(Recommendation).filter(Recommendation.investigation_id == inv.id).all()
    assert len(recs) == 1
    rec = recs[0]
    assert rec.approval_status == "PENDING_APPROVAL"
    assert rec.recommendation_type == "CONFIGURATION_CHANGE"
    assert rec.target_service_id == svc.id

@pytest.mark.asyncio
async def test_worker_validation_failure_destructive_keyword(db_session: Session):
    svc = Service(id=uuid4(), name="TestSvc", environment="prod")
    inc = Incident(id=uuid4(), title="Test", severity="P1", status="Detected", service_id=svc.id, detected_at=datetime.now(timezone.utc), last_anomaly_at=datetime.now(timezone.utc))
    inv = Investigation(id=uuid4(), incident_id=inc.id, status="complete")
    hyp = Hypothesis(id=uuid4(), investigation_id=inv.id, statement="Test statement", reasoning="Test reasoning", confidence=0.9, is_probable_root_cause=True)
    
    db_session.add_all([svc, inc, inv, hyp])
    db_session.commit()
    
    # We patch the mock provider to return a destructive keyword
    from app.investigations.llm import DevMockLLMProvider, LLMRecommendationResponse, LLMRecommendation
    original_generate = DevMockLLMProvider.generate_recommendations
    
    async def mock_bad_generate(*args, **kwargs):
        return LLMRecommendationResponse(
            recommendation=LLMRecommendation(
                title="Bad Rec",
                description="rm -rf /var/lib/data", # Destructive!
                rationale="Test",
                recommendation_type="CONFIGURATION_CHANGE",
                expected_effect="Bad things",
                risk_level="HIGH",
                confidence=0.9,
                preconditions=[],
                validation_steps=[],
                rollback_guidance="Good luck"
            )
        )
    DevMockLLMProvider.generate_recommendations = mock_bad_generate
    
    try:
        await generate_recommendation_task(inv.id, db=db_session)
    finally:
        DevMockLLMProvider.generate_recommendations = original_generate
    
    recs = db_session.query(Recommendation).filter(Recommendation.investigation_id == inv.id).all()
    assert len(recs) == 1
    assert recs[0].approval_status == "VALIDATION_FAILED"

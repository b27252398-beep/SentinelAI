import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import SessionLocal
from app.recommendations.models import Recommendation
from app.incidents.models import Incident
from app.services.models import Service
from app.investigations.models import Investigation, Hypothesis

def test_redis_failure_safe(db_session: Session):
    import app.recommendations.worker as worker
    from unittest.mock import patch
    
    with patch("redis.Redis") as mock_redis:
        mock_redis.side_effect = Exception("Connection refused")
        worker.redis_client = None
        
        investigation_id = uuid.uuid4()
        
        import asyncio
        asyncio.run(worker.generate_recommendation_task(investigation_id, db_session))
        
        recs = db_session.query(Recommendation).filter_by(investigation_id=investigation_id).all()
        assert len(recs) == 0

def test_occ_staleness(db_session: Session):
    from sqlalchemy.orm.exc import StaleDataError
    
    svc = Service(id=uuid.uuid4(), name=f"Svc_{uuid.uuid4().hex[:6]}", environment="prod")
    inc = Incident(id=uuid.uuid4(), title="Test", severity="P1", status="Detected", service_id=svc.id, detected_at=datetime.now(timezone.utc), last_anomaly_at=datetime.now(timezone.utc))
    inv = Investigation(id=uuid.uuid4(), incident_id=inc.id, status="complete")
    hyp = Hypothesis(id=uuid.uuid4(), investigation_id=inv.id, statement="Stmt", reasoning="R", confidence=0.9, is_probable_root_cause=True)
    
    rec = Recommendation(
        id=uuid.uuid4(),
        investigation_id=inv.id,
        incident_id=inc.id,
        hypothesis_id=hyp.id,
        title="Test OCC",
        description="Desc",
        rationale="Rat",
        recommendation_type="GENERIC",
        target_service_id=svc.id,
        expected_effect="Effect",
        risk_level="LOW",
        confidence=0.9,
        preconditions=[],
        validation_steps=[],
        rollback_guidance="Rollback",
        approval_status="PENDING_APPROVAL"
    )
    db_session.add_all([svc, inc, inv, hyp, rec])
    db_session.commit()
    
    # Change via ORM
    rec.approval_status = "APPROVED"
    
    # Change via raw SQL underneath
    db_session.execute(text("UPDATE recommendations SET version = version + 1 WHERE id = :id"), {"id": rec.id.hex})
    
    # Try to commit ORM
    with pytest.raises(StaleDataError):
        db_session.commit()
    db_session.rollback()

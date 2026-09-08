import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timezone

from app.investigations.worker import process_investigation
from app.incidents.models import Incident
from app.services.models import Service
from app.investigations.models import Investigation, Hypothesis

@pytest.mark.asyncio
async def test_worker_end_to_end(db_session):
    # Setup
    svc1 = Service(name="service-worker", environment="test")
    db_session.add(svc1)
    db_session.commit()
    
    now = datetime.now(timezone.utc)
    inc = Incident(
        title="Test Incident",
        service_id=svc1.id,
        severity="P3",
        status="Detected",
        detected_at=now,
        last_anomaly_at=now,
        version=1
    )
    db_session.add(inc)
    db_session.commit()
    
    inv = Investigation(incident_id=inc.id, status="pending")
    db_session.add(inv)
    db_session.commit()
    
    # Process
    await process_investigation(inv.id, db=db_session)
    
    # Check results
    db_session.refresh(inv)
    assert inv.status == "complete"
    
    hypos = db_session.query(Hypothesis).filter(Hypothesis.investigation_id == inv.id).all()
    # The Mock returns 2 hypotheses, but if there's no evidence, it might return Insufficient Evidence
    # Wait, retriever returns 0 if no telemetry, and process_investigation short circuits
    assert len(hypos) == 1
    assert hypos[0].statement == "Insufficient Evidence / No Hypotheses generated."
    assert hypos[0].is_probable_root_cause == True

@pytest.mark.asyncio
async def test_worker_with_evidence(db_session):
    from app.investigations.retriever import retrieve_evidence
    from app.telemetry.models import Telemetry
    import json
    # Setup
    svc1 = Service(name="service-worker-2", environment="test")
    db_session.add(svc1)
    db_session.commit()
    
    now = datetime.now(timezone.utc)
    inc = Incident(
        title="Test Incident 2",
        service_id=svc1.id,
        severity="P3",
        status="Detected",
        detected_at=now,
        last_anomaly_at=now,
        version=1
    )
    db_session.add(inc)
    db_session.commit()
    
    inv = Investigation(incident_id=inc.id, status="pending")
    db_session.add(inv)
    db_session.commit()
    
    t1 = Telemetry(
        id=uuid4(),
        timestamp=now,
        service_id=svc1.id,
        telemetry_type="log",
        fingerprint="f1_worker",
        raw_payload=json.dumps({"msg": "error"})
    )
    db_session.add(t1)
    db_session.commit()
    
    # Process
    await process_investigation(inv.id, db=db_session)
    
    # Check results
    db_session.refresh(inv)
    assert inv.status == "complete"
    
    hypos = db_session.query(Hypothesis).filter(Hypothesis.investigation_id == inv.id).all()
    # The mock returns 2 hypotheses.
    assert len(hypos) == 2
    
    # The first should be the one with more confidence/score
    hypos.sort(key=lambda x: x.confidence, reverse=True)
    assert hypos[0].is_probable_root_cause == True
    assert hypos[1].is_probable_root_cause == False
    
    # Check that scoring worked deterministically (Mock gives H1: 0.8+0.1=0.9, H2: 0.4+0.1-0.2=0.3)
    assert hypos[0].confidence == pytest.approx(0.9)
    assert hypos[1].confidence == pytest.approx(0.3)

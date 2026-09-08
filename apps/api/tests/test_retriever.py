import pytest
import uuid
import json
from datetime import datetime, timedelta, timezone

from app.services.models import Service
from app.incidents.models import Incident
from app.telemetry.models import Telemetry
from app.investigations.models import Investigation
from app.investigations.retriever import retrieve_evidence

def test_evidence_retrieval(db_session):
    # Setup
    svc1 = Service(name="service-a", environment="test")
    svc2 = Service(name="service-b", environment="test")
    db_session.add(svc1)
    db_session.add(svc2)
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
    
    inv = Investigation(incident_id=inc.id, status="running")
    db_session.add(inv)
    db_session.commit()
    
    # Create some telemetry
    trace_id_cross = "trace-123"
    
    # 1. In-window for svc1
    t1 = Telemetry(
        id=uuid.uuid4(),
        timestamp=now - timedelta(minutes=10),
        service_id=svc1.id,
        telemetry_type="log",
        fingerprint="f1",
        raw_payload=json.dumps({"msg": "in-window svc1"})
    )
    # 2. Out-of-window for svc1 (too old, 35m)
    t2 = Telemetry(
        id=uuid.uuid4(),
        timestamp=now - timedelta(minutes=35),
        service_id=svc1.id,
        telemetry_type="log",
        fingerprint="f2",
        raw_payload=json.dumps({"msg": "too-old"})
    )
    # 3. In-window for svc1 with trace_id
    t3 = Telemetry(
        id=uuid.uuid4(),
        timestamp=now - timedelta(minutes=5),
        service_id=svc1.id,
        telemetry_type="trace",
        trace_id=trace_id_cross,
        fingerprint="f3",
        raw_payload=json.dumps({"msg": "has-trace"})
    )
    # 4. In-window for svc2 with SAME trace_id (should be fetched via cross-service)
    t4 = Telemetry(
        id=uuid.uuid4(),
        timestamp=now - timedelta(minutes=4),
        service_id=svc2.id,
        telemetry_type="trace",
        trace_id=trace_id_cross,
        fingerprint="f4",
        raw_payload=json.dumps({"msg": "cross-service span"})
    )
    # 5. In-window for svc2 NO trace_id (should NOT be fetched)
    t5 = Telemetry(
        id=uuid.uuid4(),
        timestamp=now - timedelta(minutes=4),
        service_id=svc2.id,
        telemetry_type="log",
        fingerprint="f5",
        raw_payload=json.dumps({"msg": "irrelevant"})
    )

    
    for t in [t1, t2, t3, t4, t5]:
        db_session.add(t)
        db_session.commit()

    
    # Run retriever
    count = retrieve_evidence(db_session, inc, inv.id)

    
    assert count == 3  # t1, t3, t4
    
    from app.investigations.models import InvestigationEvidence
    evs = db_session.query(InvestigationEvidence).filter(InvestigationEvidence.investigation_id == inv.id).all()
    
    payloads = []
    for e in evs:
        p = e.deep_copied_payload
        if isinstance(p, str):
            p = json.loads(p)
        if "raw" in p:
            raw = p["raw"]
            if isinstance(raw, str):
                raw = json.loads(raw)
            payloads.append(raw.get("msg"))
        else:
            payloads.append(p.get("msg"))
    assert "in-window svc1" in payloads
    assert "has-trace" in payloads
    assert "cross-service span" in payloads
    assert "too-old" not in payloads
    assert "irrelevant" not in payloads

import uuid
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.incidents.models import Incident
from app.detection.models import AnomalyEvent
from app.telemetry.models import Telemetry
from app.investigations.models import InvestigationEvidence

# Bounded retrieval limits
MAX_ANOMALIES = 50
MAX_TELEMETRY = 1950  # 2000 total - 50 anomalies

def retrieve_evidence(db: Session, incident: Incident, investigation_id: str) -> int:
    """
    Retrieves evidence within the 30m leading / 15m trailing window of the incident.
    Returns the number of evidence records inserted.
    """
    # 1. Define window
    window_start = incident.detected_at - timedelta(minutes=30)
    window_end = incident.last_anomaly_at + timedelta(minutes=15)
    
    # We will bulk insert to avoid ORM overhead if there are many records
    evidence_to_insert = []
    
    # 2. Retrieve Anomalies
    anomalies = (
        db.query(AnomalyEvent)
        .filter(AnomalyEvent.service_id == incident.service_id)
        .filter(AnomalyEvent.window_start >= window_start)
        .filter(AnomalyEvent.window_start <= window_end)
        .order_by(AnomalyEvent.window_start.desc())
        .limit(MAX_ANOMALIES)
        .all()
    )
    
    for anomaly in anomalies:
        payload = {
            "feature": anomaly.feature,
            "severity": anomaly.severity,
            "status": anomaly.status,
            "detector_type": anomaly.detector_type,
            "evidence": anomaly.evidence
        }
        evidence_to_insert.append(
            InvestigationEvidence(
                id=uuid.uuid4(),
                investigation_id=investigation_id,
                source_type="anomaly",
                source_identifier=str(anomaly.id),
                timestamp=anomaly.window_start,
                service_id=anomaly.service_id,
                deep_copied_payload=payload
            )
        )
        
    # 3. Retrieve Telemetry for the target service
    # Only pull limited amount, order by priority conceptually, but realistically
    # we can pull a subset of errors, traces, and metrics.
    # To keep it deterministic and bounded, we pull them ordered by timestamp desc.
    telemetry_records = (
        db.query(Telemetry)
        .filter(Telemetry.service_id == incident.service_id)
        .filter(Telemetry.timestamp >= window_start)
        .filter(Telemetry.timestamp <= window_end)
        .order_by(Telemetry.timestamp.desc())
        .limit(MAX_TELEMETRY)
        .all()
    )
    
    trace_ids = set()
    
    for t in telemetry_records:
        if t.trace_id:
            trace_ids.add(t.trace_id)
            
        # raw_payload is expected to be a dict if JSONB, but if SQLite it might be stringified depending on the dialect config.
        # Ensure it's a dict for our deep copy.
        payload = t.raw_payload if isinstance(t.raw_payload, dict) else {"raw": t.raw_payload}
        
        evidence_to_insert.append(
            InvestigationEvidence(
                id=uuid.uuid4(),
                investigation_id=investigation_id,
                source_type=t.telemetry_type,
                source_identifier=str(t.id),
                timestamp=t.timestamp,
                service_id=t.service_id,
                deep_copied_payload=payload
            )
        )
        
    # 4. Cross-service trace retrieval
    # If we collected trace_ids, fetch all telemetry across ALL services for those trace_ids
    if trace_ids:
        # Bounded cross-service fetching
        remaining_budget = MAX_TELEMETRY - len(telemetry_records)
        if remaining_budget > 0:
            cross_service_spans = (
                db.query(Telemetry)
                .filter(Telemetry.trace_id.in_(list(trace_ids)))
                # Don't re-fetch the ones we already have
                .filter(Telemetry.service_id != incident.service_id)
                # Bounded by time to prevent massive out-of-bounds trace spans 
                # (though trace_id usually implies same transaction time)
                .filter(Telemetry.timestamp >= window_start)
                .filter(Telemetry.timestamp <= window_end)
                .order_by(Telemetry.timestamp.desc())
                .limit(remaining_budget)
                .all()
            )
            
            for t in cross_service_spans:
                payload = t.raw_payload if isinstance(t.raw_payload, dict) else {"raw": t.raw_payload}
                evidence_to_insert.append(
                    InvestigationEvidence(
                        id=uuid.uuid4(),
                        investigation_id=investigation_id,
                        source_type=t.telemetry_type,
                        source_identifier=str(t.id),
                        timestamp=t.timestamp,
                        service_id=t.service_id, # Original service_id preserved
                        deep_copied_payload=payload
                    )
                )

    if evidence_to_insert:
        for e in evidence_to_insert:
            db.add(e)
            db.commit()
        
    return len(evidence_to_insert)

import pytest
from datetime import datetime, timezone, timedelta
import uuid

from app.detection.models import DetectorConfig, AnomalyEvent
from app.detection.lifecycle import process_detection_result
from app.detection.schemas import DetectionResult

def setup_config(db_session, service_id):
    cfg = DetectorConfig(
        service_id=service_id,
        detector_type="DB Connection Exhaustion",
        feature="db_connections",
        aggregation_function="AVG(metric_value)",
        config={"warning_threshold": 80.0},
        cooldown_windows=3
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg

def test_anomaly_lifecycle(db_session):
    from app.services.models import Service
    svc = Service(name="Test Lifecycle", environment="test")
    db_session.add(svc)
    db_session.commit()
    
    cfg = setup_config(db_session, svc.id)
    
    # 1. Breach
    w1_start = datetime(2026, 9, 8, 10, 0, 0, tzinfo=timezone.utc)
    w1_end = w1_start + timedelta(minutes=5)
    
    res1 = DetectionResult(is_anomaly=True, severity="P3", evidence={"val": 1})
    process_detection_result(db_session, cfg, w1_start, w1_end, res1)
    
    anomalies = db_session.query(AnomalyEvent).all()
    assert len(anomalies) == 1
    an = anomalies[0]
    assert an.status == "OPEN"
    assert an.window_end.replace(tzinfo=timezone.utc) == w1_end
    
    # Idempotent retry of breach
    process_detection_result(db_session, cfg, w1_start, w1_end, res1)
    assert len(db_session.query(AnomalyEvent).all()) == 1
    
    # 2. Consecutive Breach
    w2_start = w1_end
    w2_end = w2_start + timedelta(minutes=5)
    res2 = DetectionResult(is_anomaly=True, severity="P3", evidence={"val": 2})
    process_detection_result(db_session, cfg, w2_start, w2_end, res2)
    
    db_session.refresh(an)
    assert an.window_end.replace(tzinfo=timezone.utc) == w2_end
    assert an.cooldown_count == 0
    
    # 3. Clean Window
    w3_start = w2_end
    w3_end = w3_start + timedelta(minutes=5)
    res3 = DetectionResult(is_anomaly=False, severity=None, evidence={"val": 3})
    process_detection_result(db_session, cfg, w3_start, w3_end, res3)
    
    db_session.refresh(an)
    assert an.cooldown_count == 1
    assert an.status == "OPEN"
    
    # Clean window idempotent retry
    process_detection_result(db_session, cfg, w3_start, w3_end, res3)
    db_session.refresh(an)
    assert an.cooldown_count == 1  # Should NOT double increment
    
    # 4. New Breach during cooldown resets cooldown
    w4_start = w3_end
    w4_end = w4_start + timedelta(minutes=5)
    res4 = DetectionResult(is_anomaly=True, severity="P2", evidence={"val": 4})
    process_detection_result(db_session, cfg, w4_start, w4_end, res4)
    
    db_session.refresh(an)
    assert an.cooldown_count == 0
    assert an.window_end.replace(tzinfo=timezone.utc) == w4_end
    assert an.severity == "P2"
    
    # 5. Resolution
    # Cooldown 1
    w5_start = w4_end
    w5_end = w5_start + timedelta(minutes=5)
    process_detection_result(db_session, cfg, w5_start, w5_end, res3)
    
    # Cooldown 2
    w6_start = w5_end
    w6_end = w6_start + timedelta(minutes=5)
    process_detection_result(db_session, cfg, w6_start, w6_end, res3)
    
    # Cooldown 3 (RESOLVED)
    w7_start = w6_end
    w7_end = w7_start + timedelta(minutes=5)
    process_detection_result(db_session, cfg, w7_start, w7_end, res3)
    
    db_session.refresh(an)
    assert an.cooldown_count == 3
    assert an.status == "RESOLVED"
    
    # 6. Re-breach after resolved creates NEW anomaly
    w8_start = w7_end
    w8_end = w8_start + timedelta(minutes=5)
    process_detection_result(db_session, cfg, w8_start, w8_end, res1)
    
    anomalies = db_session.query(AnomalyEvent).order_by(AnomalyEvent.created_at).all()
    assert len(anomalies) == 2
    assert anomalies[0].status == "RESOLVED"
    assert anomalies[1].status == "OPEN"

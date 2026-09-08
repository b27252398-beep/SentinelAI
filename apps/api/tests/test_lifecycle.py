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


def test_p2_consecutive_escalates_to_p1(db_session):
    """Three unbroken consecutive P2 breaches must escalate the anomaly to P1."""
    from app.services.models import Service
    svc = Service(name="P1 Escalation Svc", environment="test")
    db_session.add(svc)
    db_session.commit()

    cfg = DetectorConfig(
        service_id=svc.id,
        detector_type="API Latency",
        feature="p95_latency",
        aggregation_function="PERCENTILE_CONT(0.95)",
        config={"z_threshold": 5.0},
        cooldown_windows=3,
    )
    db_session.add(cfg)
    db_session.commit()

    w_start = datetime(2026, 9, 8, 11, 0, 0, tzinfo=timezone.utc)
    breach_p2 = DetectionResult(is_anomaly=True, severity="P2", evidence={"val": 99})

    # Breach 1 — P2 streak begins
    ws1, we1 = w_start, w_start + timedelta(minutes=5)
    process_detection_result(db_session, cfg, ws1, we1, breach_p2)
    an = db_session.query(AnomalyEvent).filter_by(service_id=svc.id).first()
    assert an.severity == "P2"

    # Breach 2 — streak continues
    ws2, we2 = we1, we1 + timedelta(minutes=5)
    process_detection_result(db_session, cfg, ws2, we2, breach_p2)
    db_session.refresh(an)
    assert an.severity == "P2"  # Still P2 — not yet 3

    # Breach 3 — streak complete → P1
    ws3, we3 = we2, we2 + timedelta(minutes=5)
    process_detection_result(db_session, cfg, ws3, we3, breach_p2)
    db_session.refresh(an)
    assert an.severity == "P1", f"Expected P1 after 3 consecutive P2s, got {an.severity}"


def test_p2_interrupted_by_clean_does_not_escalate_to_p1(db_session):
    """
    A P2 streak interrupted by a clean window must reset the consecutive counter.
    Sequence: P2 → P2 → CLEAN → P2 must NOT produce P1.
    Only three CONSECUTIVE P2 breaches may escalate to P1.
    """
    from app.services.models import Service
    svc = Service(name="P1 Non-Escalation Svc", environment="test")
    db_session.add(svc)
    db_session.commit()

    cfg = DetectorConfig(
        service_id=svc.id,
        detector_type="Memory Leak",
        feature="avg_memory_usage",
        aggregation_function="AVG(metric_value)",
        config={"z_threshold": 5.0},
        cooldown_windows=3,
    )
    db_session.add(cfg)
    db_session.commit()

    base = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
    breach_p2 = DetectionResult(is_anomaly=True, severity="P2", evidence={"val": 99})
    clean = DetectionResult(is_anomaly=False, severity=None, evidence={"val": 0})

    windows = [(base + timedelta(minutes=5 * i), base + timedelta(minutes=5 * (i + 1)))
               for i in range(4)]

    # W1: P2 — streak = 1
    process_detection_result(db_session, cfg, windows[0][0], windows[0][1], breach_p2)
    an = db_session.query(AnomalyEvent).filter_by(service_id=svc.id).first()
    assert an.severity == "P2"

    # W2: P2 — streak = 2
    process_detection_result(db_session, cfg, windows[1][0], windows[1][1], breach_p2)
    db_session.refresh(an)
    assert an.severity == "P2"

    # W3: CLEAN — streak resets to 0, cooldown increments
    process_detection_result(db_session, cfg, windows[2][0], windows[2][1], clean)
    db_session.refresh(an)
    assert an.status == "OPEN"  # Not resolved yet (cooldown_windows=3, only 1 clean)
    assert an.cooldown_count == 1

    # W4: P2 — streak is only 1 (reset by clean). Must NOT escalate to P1.
    process_detection_result(db_session, cfg, windows[3][0], windows[3][1], breach_p2)
    db_session.refresh(an)
    assert an.severity != "P1", (
        f"Interrupted P2 sequence incorrectly escalated to P1. "
        f"Severity: {an.severity}, evidence: {an.evidence}"
    )
    assert an.severity == "P2"


def test_undetermined_does_not_change_lifecycle(db_session):
    """UNDETERMINED results (insufficient data / execution failure) must not
    increment cooldown_count, trigger resolution, or create a new anomaly."""
    from app.services.models import Service
    svc = Service(name="Undetermined Test Svc", environment="test")
    db_session.add(svc)
    db_session.commit()

    cfg = DetectorConfig(
        service_id=svc.id,
        detector_type="DB Connection Exhaustion",
        feature="avg_db_connections",
        aggregation_function="AVG(metric_value)",
        config={"warning_threshold": 80.0},
        cooldown_windows=2,
    )
    db_session.add(cfg)
    db_session.commit()

    base = datetime(2026, 9, 8, 13, 0, 0, tzinfo=timezone.utc)
    breach = DetectionResult(is_anomaly=True, severity="P3", evidence={"val": 90})
    undetermined = DetectionResult(is_anomaly=False, severity=None, evidence={"status": "UNDETERMINED"})

    # W1: Open an anomaly.
    ws1, we1 = base, base + timedelta(minutes=5)
    process_detection_result(db_session, cfg, ws1, we1, breach)
    an = db_session.query(AnomalyEvent).filter_by(service_id=svc.id).first()
    assert an.status == "OPEN"
    assert an.cooldown_count == 0

    # W2: UNDETERMINED — lifecycle must be unchanged.
    ws2, we2 = we1, we1 + timedelta(minutes=5)
    process_detection_result(db_session, cfg, ws2, we2, undetermined)
    db_session.refresh(an)
    assert an.status == "OPEN", "UNDETERMINED must not resolve the anomaly"
    assert an.cooldown_count == 0, "UNDETERMINED must not increment cooldown"

    # W3: Another UNDETERMINED — still unchanged.
    ws3, we3 = we2, we2 + timedelta(minutes=5)
    process_detection_result(db_session, cfg, ws3, we3, undetermined)
    db_session.refresh(an)
    assert an.status == "OPEN"
    assert an.cooldown_count == 0

    # No new anomalies should have been created.
    total = db_session.query(AnomalyEvent).filter_by(service_id=svc.id).count()
    assert total == 1, f"Expected 1 anomaly, found {total}"

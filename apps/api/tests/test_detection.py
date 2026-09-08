import pytest
from datetime import datetime, timezone
import uuid

from app.detection.engine import (
    get_tumbling_window,
    safe_z_score,
    evaluate_z_score_detector,
    evaluate_static_threshold
)

def test_tumbling_window():
    # 10:02:30 -> 10:00:00
    t1 = datetime(2026, 9, 8, 10, 2, 30, tzinfo=timezone.utc)
    w1 = get_tumbling_window(t1)
    assert w1 == datetime(2026, 9, 8, 10, 0, 0, tzinfo=timezone.utc)
    
    # 10:05:00 -> 10:05:00
    t2 = datetime(2026, 9, 8, 10, 5, 0, tzinfo=timezone.utc)
    w2 = get_tumbling_window(t2)
    assert w2 == datetime(2026, 9, 8, 10, 5, 0, tzinfo=timezone.utc)
    
    # 10:09:59 -> 10:05:00
    t3 = datetime(2026, 9, 8, 10, 9, 59, tzinfo=timezone.utc)
    w3 = get_tumbling_window(t3)
    assert w3 == datetime(2026, 9, 8, 10, 5, 0, tzinfo=timezone.utc)

def test_safe_z_score():
    assert safe_z_score(15.0, 10.0, 2.0) == 2.5
    assert safe_z_score(15.0, 10.0, 0.0) == 50000.0  # (15 - 10) / 0.0001
    assert safe_z_score(10.0, 10.0, 0.0) == 0.0
    assert safe_z_score(float('nan'), 10.0, 2.0) == 0.0
    assert safe_z_score(15.0, float('inf'), 2.0) == 0.0

def test_z_score_detector_evaluation():
    w_start = datetime(2026, 9, 8, 10, 0, 0, tzinfo=timezone.utc)
    w_end = datetime(2026, 9, 8, 10, 5, 0, tzinfo=timezone.utc)
    c_id = str(uuid.uuid4())
    
    # Normal (z < 3.0)
    res = evaluate_z_score_detector(
        14.0, 10.0, 2.0, 5, 12, 1, 12, "test", c_id, 1, w_start, w_end
    )
    assert not res.is_anomaly
    assert res.severity is None
    
    # P4 (z = 3.0)
    res = evaluate_z_score_detector(
        16.0, 10.0, 2.0, 5, 12, 1, 12, "test", c_id, 1, w_start, w_end
    )
    assert res.is_anomaly
    assert res.severity == "P4"
    
    # P3 (z = 4.0)
    res = evaluate_z_score_detector(
        18.0, 10.0, 2.0, 5, 12, 1, 12, "test", c_id, 1, w_start, w_end
    )
    assert res.is_anomaly
    assert res.severity == "P3"
    
    # P2 (z = 5.0)
    res = evaluate_z_score_detector(
        20.0, 10.0, 2.0, 5, 12, 1, 12, "test", c_id, 1, w_start, w_end
    )
    assert res.is_anomaly
    assert res.severity == "P2"
    
    # Insufficient baseline
    res = evaluate_z_score_detector(
        20.0, 10.0, 2.0, 5, 11, 1, 12, "test", c_id, 1, w_start, w_end
    )
    assert not res.is_anomaly
    assert res.evidence["status"] == "UNDETERMINED"
    
    # Insufficient raw samples
    res = evaluate_z_score_detector(
        20.0, 10.0, 2.0, 0, 12, 1, 12, "test", c_id, 1, w_start, w_end
    )
    assert not res.is_anomaly
    assert res.evidence["status"] == "UNDETERMINED"

def test_static_threshold_evaluation():
    w_start = datetime(2026, 9, 8, 10, 0, 0, tzinfo=timezone.utc)
    w_end = datetime(2026, 9, 8, 10, 5, 0, tzinfo=timezone.utc)
    c_id = str(uuid.uuid4())
    
    config = {"warning_threshold": 80.0, "critical_threshold": 95.0}
    
    # Normal
    res = evaluate_static_threshold(70.0, 5, 1, config, "test", c_id, 1, w_start, w_end)
    assert not res.is_anomaly
    
    # Warning (exactly on boundary)
    res = evaluate_static_threshold(80.0, 5, 1, config, "test", c_id, 1, w_start, w_end)
    assert res.is_anomaly
    assert res.severity == "P3"
    assert res.evidence["threshold_type"] == "warning"
    
    # Critical (above boundary)
    res = evaluate_static_threshold(100.0, 5, 1, config, "test", c_id, 1, w_start, w_end)
    assert res.is_anomaly
    assert res.severity == "P2"
    assert res.evidence["threshold_type"] == "critical"
    
    # Insufficient raw samples
    res = evaluate_static_threshold(100.0, 0, 1, config, "test", c_id, 1, w_start, w_end)
    assert not res.is_anomaly
    assert res.evidence["status"] == "UNDETERMINED"

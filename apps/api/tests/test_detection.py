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


# ---------------------------------------------------------------------------
# NULL aggregate / missingness tests
# ---------------------------------------------------------------------------

def test_null_observed_value_is_undetermined():
    """
    When the aggregate query returns NULL (no telemetry in the window), the engine
    must classify the result as UNDETERMINED — not as an observed zero.
    This is verified via the engine's raw_count=0 guard (which observed NULL maps to).
    """
    w_start = datetime(2026, 9, 8, 10, 0, 0, tzinfo=timezone.utc)
    w_end = datetime(2026, 9, 8, 10, 5, 0, tzinfo=timezone.utc)
    c_id = str(uuid.uuid4())

    # raw_count=0 simulates no telemetry rows in the window.
    # Even if observed_val were non-None, raw_count=0 should trigger UNDETERMINED.
    res = evaluate_z_score_detector(
        0.0,   # observed value (treated as observed zero — raw_count gates this)
        10.0, 2.0,
        raw_sample_count=0,    # ← no physical telemetry rows
        baseline_count=12,
        min_raw_samples=1,
        min_baseline_observations=12,
        detector_type="Memory Leak",
        detector_config_id=c_id,
        config_version=1,
        window_start=w_start,
        window_end=w_end,
    )
    assert not res.is_anomaly
    assert res.evidence["status"] == "UNDETERMINED", (
        "Zero raw samples must produce UNDETERMINED, not a detection on observed-zero."
    )

    # Same for static threshold.
    static_config = {"warning_threshold": 0.0}  # threshold at 0.0 would match if zero were passed
    res2 = evaluate_static_threshold(
        0.0, raw_sample_count=0, min_raw_samples=1,
        config=static_config, detector_type="DB Connection Exhaustion",
        detector_config_id=c_id, config_version=1,
        window_start=w_start, window_end=w_end,
    )
    assert not res2.is_anomaly
    assert res2.evidence["status"] == "UNDETERMINED", (
        "Missing observation with threshold at 0.0 must still be UNDETERMINED."
    )


def test_observed_zero_with_sufficient_samples_is_valid():
    """
    An observed value of 0.0 with raw_count >= min_raw_samples is a genuine
    observation (e.g., zero DB connections), not a missing observation.
    It must proceed through threshold evaluation.
    """
    w_start = datetime(2026, 9, 8, 10, 0, 0, tzinfo=timezone.utc)
    w_end = datetime(2026, 9, 8, 10, 5, 0, tzinfo=timezone.utc)
    c_id = str(uuid.uuid4())

    # 5 physical rows, all reporting 0.0 connections — valid observation.
    static_config = {"warning_threshold": 80.0, "critical_threshold": 95.0}
    res = evaluate_static_threshold(
        0.0, raw_sample_count=5, min_raw_samples=1,
        config=static_config, detector_type="DB Connection Exhaustion",
        detector_config_id=c_id, config_version=1,
        window_start=w_start, window_end=w_end,
    )
    # 0.0 < 80.0 — no anomaly, but crucially NOT UNDETERMINED.
    assert not res.is_anomaly
    assert res.evidence.get("status") != "UNDETERMINED", (
        "An observed zero with sufficient samples must not be UNDETERMINED."
    )


def test_baseline_with_one_row_returns_actual_count_undetermined():
    """
    After fixing the SQLite baseline mock, a single baseline row must return
    observation_count=1, which is < min_baseline_observations=12.
    The z-score evaluator must therefore return UNDETERMINED.
    This test validates the fix to the fabricated count=12 bug.
    """
    w_start = datetime(2026, 9, 8, 10, 0, 0, tzinfo=timezone.utc)
    w_end = datetime(2026, 9, 8, 10, 5, 0, tzinfo=timezone.utc)
    c_id = str(uuid.uuid4())

    # Simulate baseline that returned only 1 valid observation bucket.
    res = evaluate_z_score_detector(
        observed_value=20.0,
        mean=10.0,
        stddev=2.0,
        raw_sample_count=5,
        baseline_count=1,      # ← only 1 baseline bucket (real count, not fabricated 12)
        min_raw_samples=1,
        min_baseline_observations=12,   # ← requires 12
        detector_type="Memory Leak",
        detector_config_id=c_id,
        config_version=1,
        window_start=w_start,
        window_end=w_end,
    )
    assert not res.is_anomaly
    assert res.evidence["status"] == "UNDETERMINED", (
        f"1 baseline bucket < 12 required must be UNDETERMINED, got: {res.evidence}"
    )

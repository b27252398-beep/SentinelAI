import math
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from app.detection.schemas import DetectionResult

def get_tumbling_window(ts: datetime) -> datetime:
    """Returns the start of the 5-minute tumbling window for a given timestamp."""
    # Ensure UTC
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    
    minute = (ts.minute // 5) * 5
    return ts.replace(minute=minute, second=0, microsecond=0)

def safe_z_score(val: float, mean: float, stddev: float) -> float:
    """Calculates z-score safely, guarding against 0 standard deviation."""
    if not math.isfinite(val) or not math.isfinite(mean) or not math.isfinite(stddev):
        return 0.0
    return (val - mean) / max(stddev, 0.0001)

def evaluate_z_score_detector(
    observed_value: float,
    mean: float,
    stddev: float,
    raw_sample_count: int,
    baseline_count: int,
    min_raw_samples: int,
    min_baseline_observations: int,
    detector_type: str,
    detector_config_id: str,
    config_version: int,
    window_start: datetime,
    window_end: datetime
) -> DetectionResult:
    """Evaluates an anomaly based on Z-Score."""
    if raw_sample_count < min_raw_samples or baseline_count < min_baseline_observations:
        return DetectionResult(is_anomaly=False, severity=None, evidence={
            "status": "UNDETERMINED",
            "reason": "insufficient_data",
            "raw_sample_count": raw_sample_count,
            "baseline_observation_count": baseline_count
        })

    z = safe_z_score(observed_value, mean, stddev)
    
    severity = None
    is_anomaly = False
    
    if z >= 5.0:
        severity = "P2"
        is_anomaly = True
    elif z >= 4.0:
        severity = "P3"
        is_anomaly = True
    elif z >= 3.0:
        severity = "P4"
        is_anomaly = True
        
    evidence = {
        "observed_value": observed_value,
        "baseline_mean": mean,
        "baseline_stddev": stddev,
        "z_score": z,
        "baseline_observation_count": baseline_count,
        "raw_sample_count": raw_sample_count,
        "detection_window_start": window_start.isoformat(),
        "detection_window_end": window_end.isoformat(),
        "detector_type": detector_type,
        "detector_config_id": str(detector_config_id),
        "config_version": config_version
    }
    
    return DetectionResult(is_anomaly=is_anomaly, severity=severity, evidence=evidence)

def evaluate_static_threshold(
    observed_value: float,
    raw_sample_count: int,
    min_raw_samples: int,
    config: Dict[str, Any],
    detector_type: str,
    detector_config_id: str,
    config_version: int,
    window_start: datetime,
    window_end: datetime
) -> DetectionResult:
    """Evaluates an anomaly based on static thresholds."""
    if raw_sample_count < min_raw_samples:
        return DetectionResult(is_anomaly=False, severity=None, evidence={
            "status": "UNDETERMINED",
            "reason": "insufficient_data",
            "raw_sample_count": raw_sample_count
        })

    warning_threshold = config.get("warning_threshold")
    critical_threshold = config.get("critical_threshold")
    
    is_anomaly = False
    severity = None
    triggered_threshold = None
    threshold_type = None

    if critical_threshold is not None and observed_value >= critical_threshold:
        is_anomaly = True
        severity = "P2"
        triggered_threshold = critical_threshold
        threshold_type = "critical"
    elif warning_threshold is not None and observed_value >= warning_threshold:
        is_anomaly = True
        severity = "P3"
        triggered_threshold = warning_threshold
        threshold_type = "warning"
        
    evidence = {
        "observed_value": observed_value,
        "raw_sample_count": raw_sample_count,
        "detection_window_start": window_start.isoformat(),
        "detection_window_end": window_end.isoformat(),
        "detector_type": detector_type,
        "detector_config_id": str(detector_config_id),
        "config_version": config_version
    }
    
    if is_anomaly:
        evidence["configured_threshold"] = triggered_threshold
        evidence["threshold_type"] = threshold_type
        
    return DetectionResult(is_anomaly=is_anomaly, severity=severity, evidence=evidence)

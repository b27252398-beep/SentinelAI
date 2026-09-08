import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.detection.models import AnomalyEvent, DetectorConfig
from app.detection.schemas import DetectionResult

def process_detection_result(
    db: Session,
    config: DetectorConfig,
    current_window_start: datetime,
    current_window_end: datetime,
    result: DetectionResult
):
    """
    Processes a detection result and updates the anomaly lifecycle.
    Idempotent by verifying if the window has already been processed.
    """
    # Find any currently OPEN anomaly for this logical detector config version
    open_anomaly = db.execute(
        select(AnomalyEvent).where(
            AnomalyEvent.service_id == config.service_id,
            AnomalyEvent.detector_config_id == config.id,
            AnomalyEvent.config_version == config.version,
            AnomalyEvent.feature == config.feature,
            AnomalyEvent.status == "OPEN"
        )
    ).scalar_one_or_none()

    if result.evidence.get("status") == "UNDETERMINED":
        # Execution failure or insufficient data.
        # Spec: Do NOT treat as clean. Do NOT increment cooldown. Do NOT resolve.
        # We essentially do nothing.
        return

    if open_anomaly:
        # SQLite drops tzinfo, restore it if missing for comparison
        open_window_end = open_anomaly.window_end
        if open_window_end.tzinfo is None:
            open_window_end = open_window_end.replace(tzinfo=timezone.utc)
            
        if result.is_anomaly:
            # Consecutive breach or new breach during cooldown
            # Extend window_end
            if current_window_end > open_window_end:
                open_anomaly.window_end = current_window_end
                
            if result.severity == "P2":
                # Check how many consecutive P2 breaches we have accumulated.
                consecutive_p2s = open_anomaly.evidence.get("consecutive_p2s", 0)
                if open_anomaly.cooldown_count > 0:
                    # A clean window interrupted the streak — reset before incrementing.
                    consecutive_p2s = 0
                
                # We only increment if this is a NEW window we are processing.
                # If we're retrying the SAME window, we shouldn't double-count.
                # Since we extended window_end above, we know it's a new window if current_window_end was > window_end.
                # Wait, we already extended it. Let's rely on idempotency:
                # We can store a list of breached windows or just assume Redis protects us.
                # For safety, let's just use a simple counter for now, updated only if we actually extend the window.
                # Actually, an easier way is to check the last evaluated window.
                last_eval = open_anomaly.evidence.get("last_evaluated_window")
                if last_eval != current_window_start.isoformat():
                    consecutive_p2s += 1
                
                open_anomaly.evidence["consecutive_p2s"] = consecutive_p2s
                
                if consecutive_p2s >= 3:
                    open_anomaly.severity = "P1"
                elif severity_rank("P2") < severity_rank(open_anomaly.severity):
                    open_anomaly.severity = "P2"
            else:
                # Not a P2, reset consecutive P2 counter but keep active severity if it's higher
                open_anomaly.evidence["consecutive_p2s"] = 0
                if severity_rank(result.severity) < severity_rank(open_anomaly.severity):
                    open_anomaly.severity = result.severity
            
            open_anomaly.cooldown_count = 0
            
            # Merge evidence safely, keeping our state keys
            consecutive_p2s = open_anomaly.evidence.get("consecutive_p2s", 0)
            open_anomaly.evidence = result.evidence
            open_anomaly.evidence["consecutive_p2s"] = consecutive_p2s
            open_anomaly.evidence["last_evaluated_window"] = current_window_start.isoformat()

        else:
            # Clean window
            last_eval = open_anomaly.evidence.get("last_evaluated_window")
            if last_eval != current_window_start.isoformat():
                open_anomaly.cooldown_count += 1
                new_evidence = dict(open_anomaly.evidence)
                new_evidence["last_evaluated_window"] = current_window_start.isoformat()
                open_anomaly.evidence = new_evidence
                
            if open_anomaly.cooldown_count >= config.cooldown_windows:
                open_anomaly.status = "RESOLVED"
                
        db.add(open_anomaly)
        db.commit()
    else:
        if result.is_anomaly:
            # Check if this anomaly already exists (idempotency for first breach)
            existing = db.execute(
                select(AnomalyEvent).where(
                    AnomalyEvent.service_id == config.service_id,
                    AnomalyEvent.detector_config_id == config.id,
                    AnomalyEvent.config_version == config.version,
                    AnomalyEvent.feature == config.feature,
                    AnomalyEvent.window_start == current_window_start
                )
            ).scalar_one_or_none()
            
            if not existing:
                # Create NEW anomaly lifecycle. If it opens as P2, count as streak=1.
                initial_evidence = dict(result.evidence)
                if result.severity == "P2":
                    initial_evidence["consecutive_p2s"] = 1
                else:
                    initial_evidence["consecutive_p2s"] = 0
                initial_evidence["last_evaluated_window"] = current_window_start.isoformat()

                new_anomaly = AnomalyEvent(
                    service_id=config.service_id,
                    detector_config_id=config.id,
                    config_version=config.version,
                    detector_type=config.detector_type,
                    feature=config.feature,
                    window_start=current_window_start,
                    window_end=current_window_end,
                    severity=result.severity,
                    status="OPEN",
                    cooldown_count=0,
                    evidence=initial_evidence
                )
                db.add(new_anomaly)
                db.commit()

def severity_rank(severity: str) -> int:
    ranks = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
    return ranks.get(severity, 99)

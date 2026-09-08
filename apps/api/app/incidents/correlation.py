"""
Deterministic event correlation engine for SentinelAI.

Correlation strategy:
- Same service_id only (no cross-service merging in MVP)
- 15-minute bounded temporal window: [detected_at, last_anomaly_at + 15min] (closed)
- Attachment state determined exclusively from incident_anomalies (no detection model mutation)
- Redis lock per service ensures at-most-one concurrent correlation execution
- PostgreSQL unique constraints are the authoritative correctness layer

Case A: No active incident → create new incident, attach as primary
Case B: Active incident, within window → attach as non-primary, maybe upgrade severity
Case C: Active incident, outside window → leave uncorrelated, do NOT create second incident
Case D: Only resolved/closed incidents → same as Case A
Case E: Concurrent creation → IntegrityError → retry as Case B
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError

from app.db.redis import get_redis_client
from app.detection.models import AnomalyEvent
from app.incidents.models import Incident, IncidentAnomaly, IncidentEvent
from app.incidents.lifecycle import higher_severity, ACTIVE_STATUSES
from app.services.models import Service

logger = logging.getLogger(__name__)

CORRELATION_WINDOW_MINUTES = 15


# ---------------------------------------------------------------------------
# Redis distributed lock — identical pattern to Detection lock
# ---------------------------------------------------------------------------

class CorrelationLock:
    def __init__(self, service_id: uuid.UUID):
        self.redis = get_redis_client()
        self.lock_key = f"lock:correlation:service:{service_id}"
        self.token = str(uuid.uuid4())
        self.release_script = self.redis.register_script("""
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
        """)

    def acquire(self, ttl_seconds: int = 30) -> bool:
        """Attempt to acquire lock via SET NX EX."""
        return bool(self.redis.set(self.lock_key, self.token, nx=True, ex=ttl_seconds))

    def release(self) -> bool:
        """Ownership-safe Lua release — only releases if we still own the token."""
        return bool(self.release_script(keys=[self.lock_key], args=[self.token]))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_tzaware(dt: datetime) -> datetime:
    """Ensure datetime is UTC-aware (SQLite drops tzinfo on read)."""
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _append_event(
    db: Session,
    incident_id,
    event_type: str,
    actor_user_id=None,
    payload: dict = None,
) -> None:
    """Append an immutable timeline event for the incident."""
    evt = IncidentEvent(
        incident_id=incident_id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        payload=payload or {},
    )
    db.add(evt)


def _get_active_incident(db: Session, service_id) -> Incident | None:
    """Find the one active incident for this service, or None."""
    return db.execute(
        select(Incident).where(
            and_(
                Incident.service_id == service_id,
                Incident.status.notin_(["Resolved", "Closed"])
            )
        )
    ).scalar_one_or_none()


def _is_already_attached(db: Session, anomaly_id) -> bool:
    """Check incident_anomalies — never touches anomaly_events directly."""
    result = db.execute(
        select(IncidentAnomaly).where(IncidentAnomaly.anomaly_id == anomaly_id)
    ).scalar_one_or_none()
    return result is not None


def _is_eligible(anomaly: AnomalyEvent, incident: Incident) -> bool:
    """
    Eligibility rule (closed interval):
      anomaly.window_start >= incident.detected_at
      AND anomaly.window_start <= incident.last_anomaly_at + 15 minutes
    """
    a_start = _ensure_tzaware(anomaly.window_start)
    i_detected = _ensure_tzaware(incident.detected_at)
    i_last = _ensure_tzaware(incident.last_anomaly_at)
    window_upper = i_last + timedelta(minutes=CORRELATION_WINDOW_MINUTES)
    return a_start >= i_detected and a_start <= window_upper


def _build_title(anomaly: AnomalyEvent, db: Session) -> str:
    svc = db.execute(
        select(Service).where(Service.id == anomaly.service_id)
    ).scalar_one_or_none()
    svc_name = svc.name if svc else str(anomaly.service_id)
    return f"{anomaly.detector_type} on {svc_name}"


# ---------------------------------------------------------------------------
# Core correlation function
# ---------------------------------------------------------------------------

def process_anomaly(db: Session, anomaly: AnomalyEvent) -> None:
    """
    Correlate one OPEN unattached anomaly to an incident.
    Called by the correlation worker after acquiring the per-service Redis lock.
    """
    a_start = _ensure_tzaware(anomaly.window_start)
    active_incident = _get_active_incident(db, anomaly.service_id)

    if active_incident is None:
        # ── Case A / Case D: No active incident → create new one ────────────
        _create_incident_and_attach(db, anomaly, a_start)
    else:
        _attach_or_hold(db, anomaly, active_incident, a_start)


def _create_incident_and_attach(
    db: Session, anomaly: AnomalyEvent, a_start: datetime
) -> None:
    """Case A: create a new incident and attach the anomaly as primary."""
    try:
        incident = Incident(
            title=_build_title(anomaly, db),
            service_id=anomaly.service_id,
            severity=anomaly.severity,
            status="Detected",
            detected_at=a_start,
            last_anomaly_at=a_start,
        )
        db.add(incident)
        db.flush()  # obtain incident.id before inserting children

        attachment = IncidentAnomaly(
            incident_id=incident.id,
            anomaly_id=anomaly.id,
            is_primary=True,
        )
        db.add(attachment)

        _append_event(db, incident.id, "incident_creation", payload={
            "anomaly_id": str(anomaly.id),
            "severity": anomaly.severity,
            "detector_type": anomaly.detector_type,
        })
        _append_event(db, incident.id, "anomaly_attached", payload={
            "anomaly_id": str(anomaly.id),
            "is_primary": True,
        })

        db.commit()
        logger.info(
            f"[correlation] Case A: created incident {incident.id} "
            f"for anomaly {anomaly.id} (service {anomaly.service_id})"
        )

    except IntegrityError:
        # Case E: concurrent worker created the incident first
        db.rollback()
        logger.info(
            f"[correlation] Case E: concurrent incident creation conflict "
            f"for service {anomaly.service_id} — retrying as Case B"
        )
        active_incident = _get_active_incident(db, anomaly.service_id)
        if active_incident:
            _attach_or_hold(db, anomaly, active_incident, a_start)
        else:
            logger.warning(
                f"[correlation] Could not find incident after IntegrityError "
                f"for service {anomaly.service_id} — anomaly {anomaly.id} remains uncorrelated"
            )


def _attach_or_hold(
    db: Session, anomaly: AnomalyEvent, incident: Incident, a_start: datetime
) -> None:
    """Case B (eligible) or Case C (outside window)."""
    if _is_eligible(anomaly, incident):
        # ── Case B: Within window → attach ──────────────────────────────────
        try:
            attachment = IncidentAnomaly(
                incident_id=incident.id,
                anomaly_id=anomaly.id,
                is_primary=False,
            )
            db.add(attachment)

            # Update last_anomaly_at if this anomaly is more recent
            i_last = _ensure_tzaware(incident.last_anomaly_at)
            if a_start > i_last:
                incident.last_anomaly_at = anomaly.window_start

            # Severity auto-upgrade (never downgrades)
            old_severity = incident.severity
            new_severity = higher_severity(old_severity, anomaly.severity)
            if new_severity != old_severity:
                incident.severity = new_severity
                _append_event(db, incident.id, "severity_upgraded", payload={
                    "old_severity": old_severity,
                    "new_severity": new_severity,
                    "triggered_by_anomaly": str(anomaly.id),
                })

            _append_event(db, incident.id, "anomaly_attached", payload={
                "anomaly_id": str(anomaly.id),
                "is_primary": False,
            })

            db.commit()
            logger.info(
                f"[correlation] Case B: attached anomaly {anomaly.id} "
                f"to incident {incident.id}"
            )

        except IntegrityError:
            # uq_incident_anomaly_id conflict — anomaly already attached; skip
            db.rollback()
            logger.info(
                f"[correlation] Anomaly {anomaly.id} already attached to an incident "
                f"— skipping (idempotent)"
            )
    else:
        # ── Case C: Outside window → hold uncorrelated ──────────────────────
        i_last = _ensure_tzaware(incident.last_anomaly_at)
        gap_seconds = (a_start - i_last).total_seconds()
        gap_minutes = gap_seconds / 60
        logger.warning(
            f"[correlation] outside_correlation_window: "
            f"anomaly {anomaly.id} not attached to incident {incident.id}, "
            f"gap={gap_minutes:.1f}m — leaving anomaly uncorrelated. "
            f"Anomaly will be re-evaluated once incident is resolved/closed."
        )
        # Anomaly remains OPEN with NO incident_anomalies entry.
        # No second active incident is created.
        # No modification to the existing incident.
        # No modification to anomaly_events.

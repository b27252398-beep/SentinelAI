"""
Correlation engine unit tests.

Tests the process_anomaly() function directly — no HTTP client.
Redis lock is mocked to always acquire (True).

Covers all Cases A–E plus severity, boundary, and idempotency scenarios.
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.services.models import Service
from app.detection.models import AnomalyEvent, DetectorConfig
from app.incidents.models import Incident, IncidentAnomaly, IncidentEvent
from app.incidents.correlation import process_anomaly, CORRELATION_WINDOW_MINUTES
from app.incidents.lifecycle import SEVERITY_RANK


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_service(db_session, name=None) -> Service:
    svc = Service(
        name=name or f"svc-{uuid.uuid4().hex[:8]}",
        environment="test",
    )
    db_session.add(svc)
    db_session.commit()
    db_session.refresh(svc)
    return svc


def _make_detector_config(db_session, service_id) -> DetectorConfig:
    cfg = DetectorConfig(
        service_id=service_id,
        detector_type="API Latency",
        feature="http.server.duration",
        aggregation_function="percentile_cont(0.95) within group (order by metric_value)",
        config={"warning_threshold": 500, "critical_threshold": 1000},
        version=1,
    )
    db_session.add(cfg)
    db_session.commit()
    db_session.refresh(cfg)
    return cfg


def _make_anomaly(
    db_session,
    service_id,
    detector_config_id,
    window_start: datetime,
    severity: str = "P3",
    status: str = "OPEN",
) -> AnomalyEvent:
    window_end = window_start + timedelta(minutes=5)
    anomaly = AnomalyEvent(
        service_id=service_id,
        detector_config_id=detector_config_id,
        config_version=1,
        detector_type="API Latency",
        feature="http.server.duration",
        window_start=window_start,
        window_end=window_end,
        severity=severity,
        status=status,
        evidence={"status": "ANOMALY", "severity": severity},
    )
    db_session.add(anomaly)
    db_session.commit()
    db_session.refresh(anomaly)
    return anomaly


def _count_incidents(db_session, service_id) -> int:
    return db_session.query(Incident).filter(Incident.service_id == service_id).count()


def _count_active_incidents(db_session, service_id) -> int:
    return (
        db_session.query(Incident)
        .filter(Incident.service_id == service_id)
        .filter(Incident.status.notin_(["Resolved", "Closed"]))
        .count()
    )


def _get_attachment(db_session, anomaly_id):
    return (
        db_session.query(IncidentAnomaly)
        .filter(IncidentAnomaly.anomaly_id == anomaly_id)
        .first()
    )


def _get_incident_events(db_session, incident_id, event_type=None):
    q = db_session.query(IncidentEvent).filter(IncidentEvent.incident_id == incident_id)
    if event_type:
        q = q.filter(IncidentEvent.event_type == event_type)
    return q.all()


# Patch Redis lock to always succeed (acquired = True) in all tests
@pytest.fixture(autouse=True)
def mock_redis_lock():
    with patch("app.incidents.correlation.CorrelationLock") as MockLock:
        instance = MagicMock()
        instance.acquire.return_value = True
        instance.release.return_value = True
        MockLock.return_value = instance
        yield MockLock


# ---------------------------------------------------------------------------
# Case A: First anomaly creates incident
# ---------------------------------------------------------------------------

def test_first_anomaly_creates_incident(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    now = datetime.now(timezone.utc)
    anomaly = _make_anomaly(db_session, svc.id, cfg.id, window_start=now)

    process_anomaly(db_session, anomaly)

    incidents = db_session.query(Incident).filter(Incident.service_id == svc.id).all()
    assert len(incidents) == 1
    assert incidents[0].status == "Detected"
    assert incidents[0].severity == "P3"


def test_first_anomaly_is_primary(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    now = datetime.now(timezone.utc)
    anomaly = _make_anomaly(db_session, svc.id, cfg.id, window_start=now)

    process_anomaly(db_session, anomaly)

    attachment = _get_attachment(db_session, anomaly.id)
    assert attachment is not None
    assert attachment.is_primary is True


def test_incident_creation_event_appended(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    now = datetime.now(timezone.utc)
    anomaly = _make_anomaly(db_session, svc.id, cfg.id, window_start=now)

    process_anomaly(db_session, anomaly)

    incident = db_session.query(Incident).filter(Incident.service_id == svc.id).first()
    events = _get_incident_events(db_session, incident.id, "incident_creation")
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Case B: Eligible anomaly attaches
# ---------------------------------------------------------------------------

def test_eligible_anomaly_attaches(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0, severity="P3")
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0 + timedelta(minutes=5), severity="P3")

    process_anomaly(db_session, a1)
    process_anomaly(db_session, a2)

    att1 = _get_attachment(db_session, a1.id)
    att2 = _get_attachment(db_session, a2.id)
    assert att1 is not None and att1.is_primary is True
    assert att2 is not None and att2.is_primary is False
    assert att1.incident_id == att2.incident_id


def test_eligible_anomaly_is_not_primary(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0)
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0 + timedelta(minutes=5))

    process_anomaly(db_session, a1)
    process_anomaly(db_session, a2)

    att2 = _get_attachment(db_session, a2.id)
    assert att2.is_primary is False


def test_eligible_anomaly_updates_last_anomaly_at(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(minutes=10)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0)
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t1)

    process_anomaly(db_session, a1)
    process_anomaly(db_session, a2)

    incident = db_session.query(Incident).filter(Incident.service_id == svc.id).first()
    db_session.refresh(incident)
    # last_anomaly_at should reflect a2's window_start
    laa = incident.last_anomaly_at
    if laa.tzinfo is None:
        laa = laa.replace(tzinfo=timezone.utc)
    assert abs((laa - t1).total_seconds()) < 1


def test_anomaly_attached_event_appended(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0)
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0 + timedelta(minutes=5))

    process_anomaly(db_session, a1)
    process_anomaly(db_session, a2)

    incident = db_session.query(Incident).filter(Incident.service_id == svc.id).first()
    events = _get_incident_events(db_session, incident.id, "anomaly_attached")
    assert len(events) == 2


# ---------------------------------------------------------------------------
# Case C: Outside window — uncorrelated
# ---------------------------------------------------------------------------

def test_outside_window_anomaly_does_not_attach(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    # a2 is 16 minutes after a1 — outside the 15-min window
    t1 = t0 + timedelta(minutes=16)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0)
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t1)

    process_anomaly(db_session, a1)
    process_anomaly(db_session, a2)

    att2 = _get_attachment(db_session, a2.id)
    assert att2 is None   # Case C: not attached


def test_outside_window_does_not_create_second_incident(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(minutes=16)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0)
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t1)

    process_anomaly(db_session, a1)
    process_anomaly(db_session, a2)

    # Only one incident — no second active incident
    total = _count_incidents(db_session, svc.id)
    active = _count_active_incidents(db_session, svc.id)
    assert total == 1
    assert active == 1


def test_uncorrelated_anomaly_remains_open(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(minutes=20)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0)
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t1)

    process_anomaly(db_session, a1)
    process_anomaly(db_session, a2)

    db_session.refresh(a2)
    assert a2.status == "OPEN"
    assert _get_attachment(db_session, a2.id) is None


# ---------------------------------------------------------------------------
# Case D: Anomaly after resolved incident → new incident
# ---------------------------------------------------------------------------

def test_anomaly_after_resolved_creates_new_incident(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0)

    process_anomaly(db_session, a1)

    # Resolve the incident manually
    incident = db_session.query(Incident).filter(Incident.service_id == svc.id).first()
    incident.status = "Resolved"
    db_session.commit()

    # New anomaly should create a new incident
    t1 = t0 + timedelta(minutes=30)
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t1)
    process_anomaly(db_session, a2)

    total = _count_incidents(db_session, svc.id)
    assert total == 2
    att2 = _get_attachment(db_session, a2.id)
    assert att2 is not None
    assert att2.is_primary is True


# ---------------------------------------------------------------------------
# Boundary tests — exact 15-minute window
# ---------------------------------------------------------------------------

def test_exact_15min_boundary_is_eligible(db_session):
    """Anomaly at exactly last_anomaly_at + 15min is ELIGIBLE (inclusive upper bound)."""
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0)

    process_anomaly(db_session, a1)

    # Exactly 15 minutes later — should be eligible
    t_boundary = t0 + timedelta(minutes=CORRELATION_WINDOW_MINUTES)
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t_boundary)
    process_anomaly(db_session, a2)

    att2 = _get_attachment(db_session, a2.id)
    assert att2 is not None, "Anomaly at exactly +15min should be eligible (inclusive)"


def test_one_second_outside_boundary_is_ineligible(db_session):
    """Anomaly at last_anomaly_at + 15min + 1sec is NOT eligible."""
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0)

    process_anomaly(db_session, a1)

    # 15 minutes + 1 second — outside the window
    t_outside = t0 + timedelta(minutes=CORRELATION_WINDOW_MINUTES, seconds=1)
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t_outside)
    process_anomaly(db_session, a2)

    att2 = _get_attachment(db_session, a2.id)
    assert att2 is None, "Anomaly 1 second past the window should NOT be eligible"


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

def test_severity_upgrade_p3_to_p2(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0, severity="P3")
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0 + timedelta(minutes=5), severity="P2")

    process_anomaly(db_session, a1)
    process_anomaly(db_session, a2)

    incident = db_session.query(Incident).filter(Incident.service_id == svc.id).first()
    db_session.refresh(incident)
    assert incident.severity == "P2"


def test_severity_no_downgrade(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0, severity="P2")
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0 + timedelta(minutes=5), severity="P4")

    process_anomaly(db_session, a1)
    process_anomaly(db_session, a2)

    incident = db_session.query(Incident).filter(Incident.service_id == svc.id).first()
    db_session.refresh(incident)
    assert incident.severity == "P2"  # Must not downgrade to P4


def test_severity_upgrade_event_appended(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0, severity="P3")
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0 + timedelta(minutes=5), severity="P1")

    process_anomaly(db_session, a1)
    process_anomaly(db_session, a2)

    incident = db_session.query(Incident).filter(Incident.service_id == svc.id).first()
    events = _get_incident_events(db_session, incident.id, "severity_upgraded")
    assert len(events) == 1
    assert events[0].payload["old_severity"] == "P3"
    assert events[0].payload["new_severity"] == "P1"


def test_no_severity_upgrade_event_when_same_severity(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0, severity="P3")
    a2 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0 + timedelta(minutes=5), severity="P3")

    process_anomaly(db_session, a1)
    process_anomaly(db_session, a2)

    incident = db_session.query(Incident).filter(Incident.service_id == svc.id).first()
    events = _get_incident_events(db_session, incident.id, "severity_upgraded")
    assert len(events) == 0


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_duplicate_processing_idempotent(db_session):
    """Calling process_anomaly twice for same anomaly produces only one attachment."""
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0)

    process_anomaly(db_session, a1)
    # Second call: anomaly is already attached; should not raise or duplicate
    process_anomaly(db_session, a1)

    # Still only one incident
    assert _count_incidents(db_session, svc.id) == 1
    # Still only one attachment
    attachments = (
        db_session.query(IncidentAnomaly)
        .filter(IncidentAnomaly.anomaly_id == a1.id)
        .all()
    )
    assert len(attachments) == 1


# ---------------------------------------------------------------------------
# Title generation
# ---------------------------------------------------------------------------

def test_incident_title_contains_service_name(db_session):
    svc = _make_service(db_session, name="auth-service")
    cfg = _make_detector_config(db_session, svc.id)
    t0 = datetime.now(timezone.utc)
    a1 = _make_anomaly(db_session, svc.id, cfg.id, window_start=t0)

    process_anomaly(db_session, a1)

    incident = db_session.query(Incident).filter(Incident.service_id == svc.id).first()
    assert "auth-service" in incident.title
    assert "API Latency" in incident.title

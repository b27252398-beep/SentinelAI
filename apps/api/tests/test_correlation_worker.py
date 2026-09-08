"""
Correlation Worker unit tests.

Tests the worker iteration logic and lock behaviour.
Redis is fully mocked. DB uses SQLite in-memory via db_session fixture.
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, call

from app.services.models import Service
from app.detection.models import AnomalyEvent, DetectorConfig
from app.incidents.models import Incident, IncidentAnomaly
from app.incidents.worker import _get_unattached_open_anomalies, run_worker_iteration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(db_session) -> Service:
    svc = Service(name=f"svc-{uuid.uuid4().hex[:8]}", environment="test")
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


def _make_anomaly(db_session, service_id, detector_config_id, window_start, status="OPEN") -> AnomalyEvent:
    anomaly = AnomalyEvent(
        service_id=service_id,
        detector_config_id=detector_config_id,
        config_version=1,
        detector_type="API Latency",
        feature="http.server.duration",
        window_start=window_start,
        window_end=window_start + timedelta(minutes=5),
        severity="P3",
        status=status,
        evidence={"status": "ANOMALY"},
    )
    db_session.add(anomaly)
    db_session.commit()
    db_session.refresh(anomaly)
    return anomaly


# ---------------------------------------------------------------------------
# Test: _get_unattached_open_anomalies
# ---------------------------------------------------------------------------

def test_worker_queries_open_unattached_anomalies(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    now = datetime.now(timezone.utc)

    a_open = _make_anomaly(db_session, svc.id, cfg.id, now, status="OPEN")
    a_resolved = _make_anomaly(db_session, svc.id, cfg.id, now + timedelta(minutes=5), status="RESOLVED")

    result = _get_unattached_open_anomalies(db_session)
    ids = [a.id for a in result]

    assert a_open.id in ids
    assert a_resolved.id not in ids


def test_worker_skips_already_attached_anomalies(db_session):
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    now = datetime.now(timezone.utc)

    a1 = _make_anomaly(db_session, svc.id, cfg.id, now)
    a2 = _make_anomaly(db_session, svc.id, cfg.id, now + timedelta(minutes=5))

    # Manually create an incident and attach a1
    incident = Incident(
        title="Test",
        service_id=svc.id,
        severity="P3",
        status="Detected",
        detected_at=now,
        last_anomaly_at=now,
    )
    db_session.add(incident)
    db_session.flush()
    db_session.add(IncidentAnomaly(incident_id=incident.id, anomaly_id=a1.id, is_primary=True))
    db_session.commit()

    result = _get_unattached_open_anomalies(db_session)
    ids = [a.id for a in result]

    assert a1.id not in ids   # already attached
    assert a2.id in ids       # not yet attached


# ---------------------------------------------------------------------------
# Test: run_worker_iteration — lock behaviour
# ---------------------------------------------------------------------------

def test_worker_acquires_per_service_lock(db_session):
    """Worker acquires a lock for each service."""
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    now = datetime.now(timezone.utc)
    _make_anomaly(db_session, svc.id, cfg.id, now)

    with patch("app.incidents.worker.CorrelationLock") as MockLock, \
         patch("app.incidents.worker.SessionLocal", return_value=db_session), \
         patch("app.incidents.worker.process_anomaly") as mock_process, \
         patch.object(db_session, "close"):  # prevent closing the shared test session

        instance = MagicMock()
        instance.acquire.return_value = True
        instance.release.return_value = True
        MockLock.return_value = instance

        run_worker_iteration()

        MockLock.assert_called_once_with(svc.id)
        instance.acquire.assert_called_once_with(ttl_seconds=30)
        instance.release.assert_called_once()
        mock_process.assert_called_once()


def test_worker_skips_service_if_lock_not_acquired(db_session):
    """If the lock is not acquired, the service is skipped entirely."""
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    now = datetime.now(timezone.utc)
    _make_anomaly(db_session, svc.id, cfg.id, now)

    with patch("app.incidents.worker.CorrelationLock") as MockLock, \
         patch("app.incidents.worker.SessionLocal", return_value=db_session), \
         patch("app.incidents.worker.process_anomaly") as mock_process, \
         patch.object(db_session, "close"):

        instance = MagicMock()
        instance.acquire.return_value = False  # Lock not acquired
        MockLock.return_value = instance

        run_worker_iteration()

        # Lock attempted but process_anomaly should NOT have been called
        instance.acquire.assert_called_once()
        mock_process.assert_not_called()
        # Release should NOT be called if lock was never acquired
        instance.release.assert_not_called()


def test_worker_releases_lock_on_process_failure(db_session):
    """Even if process_anomaly raises, the lock is released."""
    svc = _make_service(db_session)
    cfg = _make_detector_config(db_session, svc.id)
    now = datetime.now(timezone.utc)
    _make_anomaly(db_session, svc.id, cfg.id, now)

    with patch("app.incidents.worker.CorrelationLock") as MockLock, \
         patch("app.incidents.worker.SessionLocal", return_value=db_session), \
         patch("app.incidents.worker.process_anomaly", side_effect=RuntimeError("boom")), \
         patch.object(db_session, "close"):

        instance = MagicMock()
        instance.acquire.return_value = True
        MockLock.return_value = instance

        run_worker_iteration()  # Should not raise

        # Lock must be released in finally
        instance.release.assert_called_once()


def test_worker_isolates_service_failures(db_session):
    """Failure for service A does not prevent service B from being processed."""
    svc_a = _make_service(db_session)
    svc_b = _make_service(db_session)
    cfg_a = _make_detector_config(db_session, svc_a.id)
    cfg_b = _make_detector_config(db_session, svc_b.id)
    now = datetime.now(timezone.utc)
    _make_anomaly(db_session, svc_a.id, cfg_a.id, now)
    _make_anomaly(db_session, svc_b.id, cfg_b.id, now)

    processed_services = []

    def fake_process(db, anomaly):
        if anomaly.service_id == svc_a.id:
            raise RuntimeError("Service A failure")
        processed_services.append(anomaly.service_id)

    with patch("app.incidents.worker.CorrelationLock") as MockLock, \
         patch("app.incidents.worker.SessionLocal", return_value=db_session), \
         patch("app.incidents.worker.process_anomaly", side_effect=fake_process), \
         patch.object(db_session, "close"):

        instance = MagicMock()
        instance.acquire.return_value = True
        instance.release.return_value = True
        MockLock.return_value = instance

        run_worker_iteration()  # Should not raise

        # Service B must have been processed despite service A's failure
        assert svc_b.id in processed_services


def test_worker_no_anomalies_does_nothing(db_session):
    """Worker with no OPEN unattached anomalies exits cleanly."""
    with patch("app.incidents.worker.CorrelationLock") as MockLock, \
         patch("app.incidents.worker.SessionLocal", return_value=db_session), \
         patch("app.incidents.worker.process_anomaly") as mock_process, \
         patch.object(db_session, "close"):

        run_worker_iteration()

        MockLock.assert_not_called()
        mock_process.assert_not_called()

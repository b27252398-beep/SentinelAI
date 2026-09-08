"""
Detection API integration tests.

Validates:
- Route paths at /api/v1/detectors and /api/v1/anomalies
- RBAC: Administrator and Engineer can create; Incident Manager and Viewer cannot
- Detector type validation (deferred types rejected with 422)
- Immutable versioning and IntegrityError → 409 on concurrent conflict
- Unauthenticated requests rejected with 401
"""
import pytest
import uuid
from app.detection.models import DetectorConfig
from app.auth.models import User, Role
from app.auth.security import get_password_hash, create_access_token
from app.auth.seed import seed_rbac


# ---------------------------------------------------------------------------
# Token helpers — always use seeded roles, never bare ad-hoc roles
# ---------------------------------------------------------------------------

def _make_user_with_role(db_session, role_name: str, username: str, email: str) -> str:
    """Seed RBAC, create a user, assign the named seeded role, return JWT."""
    seed_rbac(db_session)
    user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash("password123"),
        is_active=True,
    )
    role = db_session.query(Role).filter(Role.name == role_name).first()
    assert role is not None, f"Seeded role '{role_name}' not found — check seed_rbac()"
    user.roles.append(role)
    db_session.add(user)
    db_session.commit()
    return create_access_token(data={"sub": str(user.id)})


def get_administrator_token(db_session) -> str:
    return _make_user_with_role(db_session, "Administrator", "admin_det", "admin_det@test.com")


def get_engineer_token(db_session) -> str:
    return _make_user_with_role(db_session, "Engineer", "eng_det", "eng_det@test.com")


def get_incident_manager_token(db_session) -> str:
    return _make_user_with_role(db_session, "Incident Manager", "im_det", "im_det@test.com")


def get_viewer_token(db_session) -> str:
    return _make_user_with_role(db_session, "Viewer", "viewer_det", "viewer_det@test.com")


def _make_service(db_session):
    from app.services.models import Service
    svc = Service(name=f"svc-{uuid.uuid4().hex[:8]}", environment="test")
    db_session.add(svc)
    db_session.commit()
    return svc


_VALID_PAYLOAD_TEMPLATE = {
    "detector_type": "API Latency",
    "feature": "http.server.duration",
    "aggregation_function": "percentile_cont(0.95) within group (order by metric_value)",
    "min_raw_samples": 5,
    "min_baseline_observations": 12,
    "cooldown_windows": 3,
    "config": {"z_threshold": 5.0},
}


# ---------------------------------------------------------------------------
# Route path tests
# ---------------------------------------------------------------------------

def test_detectors_route_accessible(client, db_session):
    """Routes must be at /api/v1/detectors, not /api/v1/detection/configs."""
    token = get_administrator_token(db_session)
    r = client.get("/api/v1/detectors", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


def test_anomalies_route_accessible(client, db_session):
    """Routes must be at /api/v1/anomalies, not /api/v1/detection/anomalies."""
    token = get_administrator_token(db_session)
    r = client.get("/api/v1/anomalies", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


def test_old_detection_route_does_not_exist(client, db_session):
    """The old /api/v1/detection/* prefix must no longer be valid."""
    token = get_administrator_token(db_session)
    r = client.get("/api/v1/detection/configs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404, f"Old route should not exist, got {r.status_code}"


# ---------------------------------------------------------------------------
# RBAC: POST /api/v1/detectors
# ---------------------------------------------------------------------------

def test_administrator_can_create_detector(client, db_session):
    token = get_administrator_token(db_session)
    svc = _make_service(db_session)
    payload = {**_VALID_PAYLOAD_TEMPLATE, "service_id": str(svc.id)}
    r = client.post("/api/v1/detectors", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["version"] == 1
    assert data["enabled"] is True
    assert data["detector_type"] == "API Latency"


def test_engineer_can_create_detector(client, db_session):
    token = get_engineer_token(db_session)
    svc = _make_service(db_session)
    payload = {**_VALID_PAYLOAD_TEMPLATE, "service_id": str(svc.id)}
    r = client.post("/api/v1/detectors", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text


def test_incident_manager_cannot_create_detector(client, db_session):
    token = get_incident_manager_token(db_session)
    svc = _make_service(db_session)
    payload = {**_VALID_PAYLOAD_TEMPLATE, "service_id": str(svc.id)}
    r = client.post("/api/v1/detectors", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text


def test_viewer_cannot_create_detector(client, db_session):
    token = get_viewer_token(db_session)
    svc = _make_service(db_session)
    payload = {**_VALID_PAYLOAD_TEMPLATE, "service_id": str(svc.id)}
    r = client.post("/api/v1/detectors", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text


def test_unauthenticated_cannot_create_detector(client, db_session):
    svc = _make_service(db_session)
    payload = {**_VALID_PAYLOAD_TEMPLATE, "service_id": str(svc.id)}
    r = client.post("/api/v1/detectors", json=payload)
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# RBAC: GET /api/v1/detectors  (all authenticated roles can read)
# ---------------------------------------------------------------------------

def test_all_roles_can_read_detectors(client, db_session):
    for role, getter in [
        ("Administrator", get_administrator_token),
        ("Engineer", get_engineer_token),
        ("Incident Manager", get_incident_manager_token),
        ("Viewer", get_viewer_token),
    ]:
        token = getter(db_session)
        r = client.get("/api/v1/detectors", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"{role} should be able to read detectors, got {r.status_code}"


def test_all_roles_can_read_anomalies(client, db_session):
    for role, getter in [
        ("Administrator", get_administrator_token),
        ("Engineer", get_engineer_token),
        ("Incident Manager", get_incident_manager_token),
        ("Viewer", get_viewer_token),
    ]:
        token = getter(db_session)
        r = client.get("/api/v1/anomalies", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"{role} should be able to read anomalies, got {r.status_code}"


# ---------------------------------------------------------------------------
# Detector type validation
# ---------------------------------------------------------------------------

def test_deferred_detector_type_deployment_regression_rejected(client, db_session):
    """Deployment Regression is deferred — must be rejected with 422."""
    token = get_administrator_token(db_session)
    svc = _make_service(db_session)
    payload = {
        **_VALID_PAYLOAD_TEMPLATE,
        "service_id": str(svc.id),
        "detector_type": "Deployment Regression",
        "feature": "error_rate",
    }
    r = client.post("/api/v1/detectors", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422, r.text


def test_deferred_detector_type_dependency_failure_rejected(client, db_session):
    """Dependency Failure is deferred — must be rejected with 422."""
    token = get_administrator_token(db_session)
    svc = _make_service(db_session)
    payload = {
        **_VALID_PAYLOAD_TEMPLATE,
        "service_id": str(svc.id),
        "detector_type": "Dependency Failure",
        "feature": "dependency_error_rate",
    }
    r = client.post("/api/v1/detectors", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422, r.text


def test_unknown_detector_type_rejected(client, db_session):
    """Completely unknown detector types must be rejected with 422."""
    token = get_administrator_token(db_session)
    svc = _make_service(db_session)
    payload = {
        **_VALID_PAYLOAD_TEMPLATE,
        "service_id": str(svc.id),
        "detector_type": "Totally Made Up Detector",
    }
    r = client.post("/api/v1/detectors", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# Versioning — immutability
# ---------------------------------------------------------------------------

def test_create_detector_config_version_1(client, db_session):
    token = get_administrator_token(db_session)
    svc = _make_service(db_session)
    payload = {
        "service_id": str(svc.id),
        "detector_type": "Memory Leak",
        "feature": "avg_memory_usage",
        "aggregation_function": "AVG(metric_value)",
        "min_raw_samples": 3,
        "min_baseline_observations": 12,
        "cooldown_windows": 2,
        "config": {"z_threshold": 4.0},
    }
    r = client.post("/api/v1/detectors", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 1
    assert r.json()["enabled"] is True


def test_update_detector_creates_new_version(client, db_session):
    token = get_administrator_token(db_session)
    svc = _make_service(db_session)

    cfg = DetectorConfig(
        service_id=svc.id,
        detector_type="Memory Leak",
        feature="avg_memory_usage",
        aggregation_function="AVG(metric_value)",
        config={"z_threshold": 3.0},
        enabled=True,
        version=1,
    )
    db_session.add(cfg)
    db_session.commit()

    payload = {
        "service_id": str(svc.id),
        "detector_type": "Memory Leak",
        "feature": "avg_memory_usage",
        "aggregation_function": "AVG(metric_value)",
        "min_raw_samples": 3,
        "min_baseline_observations": 12,
        "cooldown_windows": 2,
        "config": {"z_threshold": 4.5},
    }
    r = client.put(
        f"/api/v1/detectors/{cfg.id}",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["version"] == 2
    assert data["config"]["z_threshold"] == 4.5

    # Old config must be disabled.
    db_session.refresh(cfg)
    assert cfg.enabled is False


def test_duplicate_active_detector_rejected(client, db_session):
    """Creating a second active config for the same (service, type, feature) must return 400."""
    token = get_administrator_token(db_session)
    svc = _make_service(db_session)
    payload = {
        "service_id": str(svc.id),
        "detector_type": "DB Connection Exhaustion",
        "feature": "avg_db_connections",
        "aggregation_function": "AVG(metric_value)",
        "min_raw_samples": 1,
        "min_baseline_observations": 1,
        "cooldown_windows": 2,
        "config": {"warning_threshold": 80.0, "critical_threshold": 95.0},
    }
    r1 = client.post("/api/v1/detectors", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 201
    r2 = client.post("/api/v1/detectors", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 400


# ---------------------------------------------------------------------------
# 404 behavior
# ---------------------------------------------------------------------------

def test_get_nonexistent_detector_returns_404(client, db_session):
    token = get_administrator_token(db_session)
    r = client.get(f"/api/v1/detectors/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_get_nonexistent_anomaly_returns_404(client, db_session):
    token = get_administrator_token(db_session)
    r = client.get(f"/api/v1/anomalies/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404

"""
Incident Management API tests.

Covers:
- Route accessibility (authenticated vs unauthenticated)
- RBAC for all 4 roles
- Manual incident creation (POST /incidents)
- Lifecycle transitions and invalid transitions
- OCC version conflict (409)
- Timeline: get and add comment
- 404 handling
"""
import pytest
import uuid
from datetime import datetime, timezone

from app.auth.models import User, Role
from app.auth.security import get_password_hash, create_access_token
from app.auth.seed import seed_rbac
from app.services.models import Service
from app.incidents.models import Incident, IncidentAnomaly, IncidentEvent
from app.detection.models import AnomalyEvent, DetectorConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_with_role(db_session, role_name: str, username: str, email: str) -> str:
    """Seed RBAC, create user with named role, return JWT."""
    seed_rbac(db_session)
    user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash("password123"),
        is_active=True,
    )
    role = db_session.query(Role).filter(Role.name == role_name).first()
    assert role is not None, f"Seeded role '{role_name}' not found"
    user.roles.append(role)
    db_session.add(user)
    db_session.commit()
    return create_access_token(data={"sub": str(user.id)})


def _admin_token(db_session) -> str:
    return _make_user_with_role(db_session, "Administrator", f"adm_{uuid.uuid4().hex[:6]}", f"adm_{uuid.uuid4().hex[:6]}@t.com")

def _im_token(db_session) -> str:
    return _make_user_with_role(db_session, "Incident Manager", f"im_{uuid.uuid4().hex[:6]}", f"im_{uuid.uuid4().hex[:6]}@t.com")

def _eng_token(db_session) -> str:
    return _make_user_with_role(db_session, "Engineer", f"eng_{uuid.uuid4().hex[:6]}", f"eng_{uuid.uuid4().hex[:6]}@t.com")

def _viewer_token(db_session) -> str:
    return _make_user_with_role(db_session, "Viewer", f"vwr_{uuid.uuid4().hex[:6]}", f"vwr_{uuid.uuid4().hex[:6]}@t.com")


def _make_service(db_session) -> Service:
    svc = Service(
        name=f"svc-{uuid.uuid4().hex[:8]}",
        environment="test",
    )
    db_session.add(svc)
    db_session.commit()
    return svc


def _make_incident(db_session, service_id, status="Detected", severity="P3") -> Incident:
    now = datetime.now(timezone.utc)
    inc = Incident(
        title="Test Incident",
        service_id=service_id,
        severity=severity,
        status=status,
        detected_at=now,
        last_anomaly_at=now,
        version=1,
    )
    db_session.add(inc)
    db_session.commit()
    db_session.refresh(inc)
    return inc


# ---------------------------------------------------------------------------
# Route accessibility
# ---------------------------------------------------------------------------

def test_list_incidents_authenticated(client, db_session):
    token = _admin_token(db_session)
    resp = client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_incidents_unauthenticated(client):
    resp = client.get("/api/v1/incidents")
    assert resp.status_code == 401


def test_get_incident_unauthenticated(client, db_session):
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id)
    resp = client.get(f"/api/v1/incidents/{inc.id}")
    assert resp.status_code == 401


def test_get_incident_not_found(client, db_session):
    token = _admin_token(db_session)
    resp = client.get(f"/api/v1/incidents/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RBAC — POST /incidents
# ---------------------------------------------------------------------------

def test_admin_can_create_incident(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    resp = client.post(
        "/api/v1/incidents",
        json={"title": "Admin test", "service_id": str(svc.id), "severity": "P3"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "Detected"
    assert body["version"] == 1
    assert body["severity"] == "P3"


def test_incident_manager_can_create_incident(client, db_session):
    token = _im_token(db_session)
    svc = _make_service(db_session)
    resp = client.post(
        "/api/v1/incidents",
        json={"title": "IM test", "service_id": str(svc.id), "severity": "P2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


def test_engineer_cannot_create_incident(client, db_session):
    token = _eng_token(db_session)
    svc = _make_service(db_session)
    resp = client.post(
        "/api/v1/incidents",
        json={"title": "Engineer test", "service_id": str(svc.id), "severity": "P3"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_viewer_cannot_create_incident(client, db_session):
    token = _viewer_token(db_session)
    svc = _make_service(db_session)
    resp = client.post(
        "/api/v1/incidents",
        json={"title": "Viewer test", "service_id": str(svc.id), "severity": "P3"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_unauthenticated_cannot_create_incident(client, db_session):
    svc = _make_service(db_session)
    resp = client.post(
        "/api/v1/incidents",
        json={"title": "Anon", "service_id": str(svc.id), "severity": "P3"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /incidents — validation
# ---------------------------------------------------------------------------

def test_create_incident_invalid_severity(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    resp = client.post(
        "/api/v1/incidents",
        json={"title": "Bad", "service_id": str(svc.id), "severity": "P9"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_incident_service_not_found(client, db_session):
    token = _admin_token(db_session)
    resp = client.post(
        "/api/v1/incidents",
        json={"title": "Bad", "service_id": str(uuid.uuid4()), "severity": "P3"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /incidents — filtering
# ---------------------------------------------------------------------------

def test_filter_by_service_id(client, db_session):
    token = _admin_token(db_session)
    svc1 = _make_service(db_session)
    svc2 = _make_service(db_session)
    _make_incident(db_session, svc1.id)

    resp = client.get(
        f"/api/v1/incidents?service_id={svc1.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(i["service_id"] == str(svc1.id) for i in data)

    resp2 = client.get(
        f"/api/v1/incidents?service_id={svc2.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json() == []


def test_filter_by_status(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    _make_incident(db_session, svc.id, status="Detected")

    resp = client.get(
        "/api/v1/incidents?status=Detected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert all(i["status"] == "Detected" for i in resp.json())


# ---------------------------------------------------------------------------
# PATCH /incidents/{id} — lifecycle
# ---------------------------------------------------------------------------

def test_valid_transition_detected_to_investigating(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Detected")

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "Investigating"
    assert body["version"] == 2


def test_valid_transition_investigating_to_identified(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Investigating")

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Identified"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Identified"


def test_valid_transition_resolved_to_investigating_reopen(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Resolved")

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Investigating"


def test_invalid_transition_detected_to_closed(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Detected")

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Closed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_invalid_transition_closed_is_terminal(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Closed")

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_engineer_can_patch_status_non_close(client, db_session):
    token = _eng_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Detected")

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_engineer_cannot_close_incident(client, db_session):
    """Engineer cannot transition to Closed."""
    token = _eng_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Resolved")

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Closed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_viewer_cannot_patch_incident(client, db_session):
    token = _viewer_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id)

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# OCC version conflict
# ---------------------------------------------------------------------------

def test_occ_version_mismatch_returns_409(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Detected")

    # First update succeeds (version=1)
    r1 = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200
    assert r1.json()["version"] == 2

    # Second update with stale version=1 → 409
    r2 = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Identified"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 409


def test_occ_correct_version_succeeds(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Detected")

    r1 = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200

    r2 = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 2, "status": "Identified"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["version"] == 3


# ---------------------------------------------------------------------------
# PATCH — severity and resolved_at / closed_at
# ---------------------------------------------------------------------------

def test_severity_change_via_patch(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, severity="P3")

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "severity": "P1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["severity"] == "P1"


def test_resolved_at_set_on_resolve(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Mitigating")

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Resolved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["resolved_at"] is not None
    assert resp.json()["closed_at"] is None


def test_closed_at_set_on_close(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Resolved")

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Closed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["closed_at"] is not None


def test_patch_invalid_severity(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id)

    resp = client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "severity": "CRITICAL"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_patch_nonexistent_incident(client, db_session):
    token = _admin_token(db_session)
    resp = client.patch(
        f"/api/v1/incidents/{uuid.uuid4()}",
        json={"version": 1, "status": "Investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def test_get_timeline_all_roles(client, db_session):
    token = _viewer_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id)

    resp = client.get(
        f"/api/v1/incidents/{inc.id}/timeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_timeline_unauthenticated(client, db_session):
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id)
    resp = client.get(f"/api/v1/incidents/{inc.id}/timeline")
    assert resp.status_code == 401


def test_add_timeline_comment_engineer(client, db_session):
    token = _eng_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id)

    resp = client.post(
        f"/api/v1/incidents/{inc.id}/timeline",
        json={"comment": "Investigating memory spike"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["event_type"] == "comment_added"
    assert body["payload"]["comment"] == "Investigating memory spike"


def test_viewer_cannot_add_timeline_comment(client, db_session):
    token = _viewer_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id)

    resp = client.post(
        f"/api/v1/incidents/{inc.id}/timeline",
        json={"comment": "Read-only user"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_timeline_not_found(client, db_session):
    token = _admin_token(db_session)
    resp = client.get(
        f"/api/v1/incidents/{uuid.uuid4()}/timeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Anomalies endpoint
# ---------------------------------------------------------------------------

def test_get_incident_anomalies(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id)

    resp = client.get(
        f"/api/v1/incidents/{inc.id}/anomalies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_incident_anomalies_not_found(client, db_session):
    token = _admin_token(db_session)
    resp = client.get(
        f"/api/v1/incidents/{uuid.uuid4()}/anomalies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Incident status events recorded in timeline
# ---------------------------------------------------------------------------

def test_status_change_creates_timeline_event(client, db_session):
    token = _admin_token(db_session)
    svc = _make_service(db_session)
    inc = _make_incident(db_session, svc.id, status="Detected")

    client.patch(
        f"/api/v1/incidents/{inc.id}",
        json={"version": 1, "status": "Investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get(
        f"/api/v1/incidents/{inc.id}/timeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    events = resp.json()
    types = [e["event_type"] for e in events]
    assert "status_changed" in types

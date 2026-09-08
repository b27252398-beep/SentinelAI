import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.auth.models import User, Role
from app.auth.security import get_password_hash, create_access_token
from app.auth.seed import seed_rbac
from app.services.models import Service
from app.incidents.models import Incident
from app.investigations.models import Investigation

def _make_user_with_role(db_session, role_name: str, username: str, email: str) -> str:
    seed_rbac(db_session)
    user = User(username=username, email=email, hashed_password=get_password_hash("password123"), is_active=True)
    role = db_session.query(Role).filter(Role.name == role_name).first()
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

def _make_incident(db_session) -> Incident:
    svc = Service(name=f"svc-{uuid.uuid4().hex[:8]}", environment="test")
    db_session.add(svc)
    db_session.commit()
    now = datetime.now(timezone.utc)
    inc = Incident(
        title="Test Incident",
        service_id=svc.id,
        severity="P3",
        status="Detected",
        detected_at=now,
        last_anomaly_at=now,
        version=1
    )
    db_session.add(inc)
    db_session.commit()
    db_session.refresh(inc)
    return inc

def _make_investigation(db_session, incident_id, status="pending") -> Investigation:
    inv = Investigation(incident_id=incident_id, status=status)
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv

def test_start_investigation(client: TestClient, db_session):
    incident = _make_incident(db_session)
    resp = client.post(
        f"/api/v1/incidents/{incident.id}/investigations",
        headers={"Authorization": f"Bearer {_admin_token(db_session)}"}
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending"
    assert data["incident_id"] == str(incident.id)

def test_retry_investigation(client, db_session):
    incident = _make_incident(db_session)
    inv = _make_investigation(db_session, incident.id, status="failed")
    
    resp = client.post(
        f"/api/v1/investigations/{inv.id}/retry",
        headers={"Authorization": f"Bearer {_admin_token(db_session)}"}
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["id"] != str(inv.id)
    assert data["status"] == "pending"

def test_get_investigation(client, db_session):
    incident = _make_incident(db_session)
    inv = _make_investigation(db_session, incident.id)
    
    resp = client.get(
        f"/api/v1/investigations/{inv.id}",
        headers={"Authorization": f"Bearer {_admin_token(db_session)}"}
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(inv.id)

def test_rbac_accept_rca_engineer_allowed(client, db_session):
    incident = _make_incident(db_session)
    inv = _make_investigation(db_session, incident.id, status="complete")
    
    resp = client.post(
        f"/api/v1/investigations/{inv.id}/rca/accept",
        headers={"Authorization": f"Bearer {_eng_token(db_session)}"}
    )
    assert resp.status_code == 200
    assert resp.json()["rca_status"] == "accepted"

def test_rbac_reject_rca_manager_allowed(client, db_session):
    incident = _make_incident(db_session)
    inv = _make_investigation(db_session, incident.id, status="complete")
    
    resp = client.post(
        f"/api/v1/investigations/{inv.id}/rca/reject",
        json={"rationale": "Does not explain the downstream failure."},
        headers={"Authorization": f"Bearer {_im_token(db_session)}"}
    )
    assert resp.status_code == 200
    assert resp.json()["rca_status"] == "rejected"

def test_rbac_viewer_forbidden(client, db_session):
    incident = _make_incident(db_session)
    inv = _make_investigation(db_session, incident.id, status="complete")
    
    resp = client.post(
        f"/api/v1/investigations/{inv.id}/rca/accept",
        headers={"Authorization": f"Bearer {_viewer_token(db_session)}"}
    )
    assert resp.status_code == 403

def test_idempotency_prevent_duplicate_running(client, db_session):
    incident = _make_incident(db_session)
    _make_investigation(db_session, incident.id, status="running")
    
    resp = client.post(
        f"/api/v1/incidents/{incident.id}/investigations",
        headers={"Authorization": f"Bearer {_admin_token(db_session)}"}
    )
    assert resp.status_code == 409

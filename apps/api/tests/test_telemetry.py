import pytest
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.services.models import Service
from app.telemetry.models import MachineCredential
from app.telemetry.auth import generate_api_key, hash_secret
from app.auth.security import create_access_token
from app.auth.models import User, Role
from app.auth.seed import seed_rbac

# --- Helpers ---

def setup_service(db_session, name="Test Service", is_active=True) -> Service:
    svc = Service(name=name, environment="production", is_active=is_active)
    db_session.add(svc)
    db_session.commit()
    return svc

def setup_credential(db_session, service_id=None, is_active=True):
    prefix, secret = generate_api_key()
    cred = MachineCredential(
        name="Test Cred",
        service_id=service_id,
        key_prefix=prefix,
        api_key_hash=hash_secret(secret),
        is_active=is_active
    )
    db_session.add(cred)
    db_session.commit()
    return f"{prefix}.{secret}"

def setup_user_with_role(db_session, role_name):
    seed_rbac(db_session)
    user = User(username=f"user_{role_name.replace(' ', '_')}", email=f"{role_name.replace(' ', '_')}@test.com", hashed_password="pass")
    role = db_session.query(Role).filter(Role.name == role_name).first()
    user.roles.append(role)
    db_session.add(user)
    db_session.commit()
    return create_access_token(data={"sub": str(user.id)})

def now_utc():
    return datetime.now(timezone.utc)

def generate_event(service_id: uuid.UUID, ts_offset_hours: int = 0, trace_id=None):
    ts = now_utc() + timedelta(hours=ts_offset_hours)
    return {
        "service_id": str(service_id),
        "timestamp": ts.isoformat(),
        "telemetry_type": "log",
        "trace_id": trace_id,
        "raw_payload": {"msg": "test", "time": ts.isoformat()}
    }

# --- Tests ---

def test_machine_credential_creation(client, db_session):
    admin_token = setup_user_with_role(db_session, "Administrator")
    
    resp = client.post(
        "/api/v1/telemetry/credentials",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "test-cred"}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "secret" in data
    assert "key_prefix" in data
    assert data["service_id"] is None

def test_ingest_auth_failures(client, db_session):
    svc = setup_service(db_session)
    valid_cred = setup_credential(db_session, svc.id)
    inactive_cred = setup_credential(db_session, svc.id, is_active=False)
    
    batch = {"events": [generate_event(svc.id)]}
    
    # Missing credential
    assert client.post("/api/v1/telemetry/ingest", json=batch).status_code == 401
    
    # Malformed credential
    assert client.post("/api/v1/telemetry/ingest", headers={"Authorization": "Bearer not.valid"}, json=batch).status_code == 401
    
    # Inactive credential
    assert client.post("/api/v1/telemetry/ingest", headers={"Authorization": f"Bearer {inactive_cred}"}, json=batch).status_code == 403

def test_ingest_authorization_scope(client, db_session):
    svc1 = setup_service(db_session, "svc1")
    svc2 = setup_service(db_session, "svc2")
    
    scoped_cred = setup_credential(db_session, svc1.id)
    global_cred = setup_credential(db_session, None)
    
    # Scoped credential for own service -> OK
    assert client.post("/api/v1/telemetry/ingest", headers={"Authorization": f"Bearer {scoped_cred}"}, json={"events": [generate_event(svc1.id)]}).status_code == 200
    
    # Scoped credential for another service -> 403
    assert client.post("/api/v1/telemetry/ingest", headers={"Authorization": f"Bearer {scoped_cred}"}, json={"events": [generate_event(svc2.id)]}).status_code == 403
    
    # Global credential for any service -> OK
    assert client.post("/api/v1/telemetry/ingest", headers={"Authorization": f"Bearer {global_cred}"}, json={"events": [generate_event(svc1.id), generate_event(svc2.id)]}).status_code == 200

def test_archived_service_rejection(client, db_session):
    svc = setup_service(db_session, is_active=False)
    global_cred = setup_credential(db_session)
    
    resp = client.post(
        "/api/v1/telemetry/ingest",
        headers={"Authorization": f"Bearer {global_cred}"},
        json={"events": [generate_event(svc.id)]}
    )
    assert resp.status_code == 403
    assert "inactive or archived" in resp.json()["detail"]

def test_timestamp_window_validation(client, db_session):
    svc = setup_service(db_session)
    cred = setup_credential(db_session, svc.id)
    
    too_old = generate_event(svc.id, ts_offset_hours=-8*24)
    too_new = generate_event(svc.id, ts_offset_hours=3*24)
    
    resp = client.post("/api/v1/telemetry/ingest", headers={"Authorization": f"Bearer {cred}"}, json={"events": [too_old]})
    assert resp.status_code == 422
    
    resp = client.post("/api/v1/telemetry/ingest", headers={"Authorization": f"Bearer {cred}"}, json={"events": [too_new]})
    assert resp.status_code == 422

def test_ingest_idempotency_and_duplicates(client, db_session):
    svc = setup_service(db_session)
    cred = setup_credential(db_session, svc.id)
    
    event = generate_event(svc.id)
    
    # First ingest
    resp = client.post(
        "/api/v1/telemetry/ingest",
        headers={"Authorization": f"Bearer {cred}"},
        json={"events": [event]}
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1
    assert resp.json()["duplicates"] == 0
    
    # Second ingest exact same event
    resp2 = client.post(
        "/api/v1/telemetry/ingest",
        headers={"Authorization": f"Bearer {cred}"},
        json={"events": [event]}
    )
    assert resp2.status_code == 200
    assert resp2.json()["accepted"] == 0
    assert resp2.json()["duplicates"] == 1
    
    # Mixed batch
    event2 = generate_event(svc.id, trace_id="12345678901234567890123456789012")
    resp3 = client.post(
        "/api/v1/telemetry/ingest",
        headers={"Authorization": f"Bearer {cred}"},
        json={"events": [event, event2]}
    )
    assert resp3.status_code == 200
    assert resp3.json()["accepted"] == 1
    assert resp3.json()["duplicates"] == 1

def test_human_query_endpoints(client, db_session):
    svc = setup_service(db_session)
    cred = setup_credential(db_session, svc.id)
    viewer_token = setup_user_with_role(db_session, "Viewer")
    
    event1 = generate_event(svc.id)
    client.post("/api/v1/telemetry/ingest", headers={"Authorization": f"Bearer {cred}"}, json={"events": [event1]})
    
    resp = client.get("/api/v1/telemetry", headers={"Authorization": f"Bearer {viewer_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    
    t_id = data[0]["id"]
    
    resp_detail = client.get(f"/api/v1/telemetry/{t_id}", headers={"Authorization": f"Bearer {viewer_token}"})
    assert resp_detail.status_code == 200
    assert resp_detail.json()["id"] == t_id

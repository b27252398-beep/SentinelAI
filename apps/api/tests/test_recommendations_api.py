import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.models import User, Role
from app.auth.security import get_password_hash, create_access_token
from app.auth.seed import seed_rbac
from app.services.models import Service
from app.incidents.models import Incident
from app.investigations.models import Investigation, Hypothesis
from app.recommendations.models import Recommendation

def _make_user_with_role(db_session, role_name: str, username: str, email: str):
    seed_rbac(db_session)
    user = User(username=username, email=email, hashed_password=get_password_hash("password123"), is_active=True)
    role = db_session.query(Role).filter(Role.name == role_name).first()
    user.roles.append(role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(data={"sub": str(user.id)})
    return user, token

def setup_test_data(db_session: Session):
    admin_user, admin_token = _make_user_with_role(db_session, "Administrator", f"adm_{uuid.uuid4().hex[:6]}", f"adm_{uuid.uuid4().hex[:6]}@t.com")
    im_user, im_token = _make_user_with_role(db_session, "Incident Manager", f"im_{uuid.uuid4().hex[:6]}", f"im_{uuid.uuid4().hex[:6]}@t.com")
    eng_user, eng_token = _make_user_with_role(db_session, "Engineer", f"eng_{uuid.uuid4().hex[:6]}", f"eng_{uuid.uuid4().hex[:6]}@t.com")
    viewer_user, viewer_token = _make_user_with_role(db_session, "Viewer", f"v_{uuid.uuid4().hex[:6]}", f"v_{uuid.uuid4().hex[:6]}@t.com")
    
    svc = Service(id=uuid.uuid4(), name=f"RecSvc_{uuid.uuid4().hex[:6]}", environment="production")
    inc = Incident(id=uuid.uuid4(), title="Test", severity="P1", status="Detected", service_id=svc.id, detected_at=datetime.now(timezone.utc), last_anomaly_at=datetime.now(timezone.utc))
    inv = Investigation(id=uuid.uuid4(), incident_id=inc.id, status="complete")
    
    hyp = Hypothesis(id=uuid.uuid4(), investigation_id=inv.id, statement="Test statement", reasoning="Test reasoning", confidence=0.9, is_probable_root_cause=True)
    
    db_session.add_all([svc, inc, inv, hyp])
    db_session.commit()
    
    return {
        "admin_user": admin_user, "admin_token": admin_token,
        "manager_user": im_user, "manager_token": im_token,
        "engineer_user": eng_user, "engineer_token": eng_token,
        "viewer_user": viewer_user, "viewer_token": viewer_token,
        "service": svc,
        "incident": inc,
        "investigation": inv,
        "hypothesis": hyp
    }

def test_generate_recommendations_success(client: TestClient, db_session: Session):
    data = setup_test_data(db_session)
    client.headers.update({"Authorization": f"Bearer {data['engineer_token']}"})
    
    resp = client.post(f"/api/v1/investigations/{data['investigation'].id}/recommendations")
    assert resp.status_code == 202

def test_generate_recommendations_low_rca(client: TestClient, db_session: Session):
    data = setup_test_data(db_session)
    data["hypothesis"].confidence = 0.3
    db_session.commit()
    
    client.headers.update({"Authorization": f"Bearer {data['manager_token']}"})
    resp = client.post(f"/api/v1/investigations/{data['investigation'].id}/recommendations")
    assert resp.status_code == 422
    assert "LOW_RCA_CONFIDENCE" in resp.json()["detail"]

def test_generate_recommendations_viewer_forbidden(client: TestClient, db_session: Session):
    data = setup_test_data(db_session)
    client.headers.update({"Authorization": f"Bearer {data['viewer_token']}"})
    resp = client.post(f"/api/v1/investigations/{data['investigation'].id}/recommendations")
    assert resp.status_code == 403

def test_approve_recommendation(client: TestClient, db_session: Session):
    data = setup_test_data(db_session)
    
    rec = Recommendation(
        id=uuid.uuid4(),
        investigation_id=data["investigation"].id,
        incident_id=data["incident"].id,
        hypothesis_id=data["hypothesis"].id,
        title="Test Rec",
        description="Test desc",
        rationale="Test rat",
        recommendation_type="CONFIGURATION_CHANGE",
        target_service_id=data["service"].id,
        expected_effect="Fixes it",
        risk_level="LOW",
        confidence=0.9,
        preconditions=[],
        validation_steps=["Step 1"],
        rollback_guidance="Rollback steps",
        approval_status="PENDING_APPROVAL"
    )
    db_session.add(rec)
    db_session.commit()
    
    client.headers.update({"Authorization": f"Bearer {data['engineer_token']}"})
    resp = client.post(f"/api/v1/recommendations/{rec.id}/approve", json={"rationale": "I like it"})
    assert resp.status_code == 403
    
    client.headers.update({"Authorization": f"Bearer {data['manager_token']}"})
    resp = client.post(f"/api/v1/recommendations/{rec.id}/approve", json={"rationale": "Good to go"})
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "APPROVED"
    assert resp.json()["decided_by"] == str(data["manager_user"].id)

def test_reject_recommendation(client: TestClient, db_session: Session):
    data = setup_test_data(db_session)
    
    rec = Recommendation(
        id=uuid.uuid4(),
        investigation_id=data["investigation"].id,
        incident_id=data["incident"].id,
        hypothesis_id=data["hypothesis"].id,
        title="Test Rec",
        description="Test desc",
        rationale="Test rat",
        recommendation_type="CONFIGURATION_CHANGE",
        target_service_id=data["service"].id,
        expected_effect="Fixes it",
        risk_level="LOW",
        confidence=0.9,
        preconditions=[],
        validation_steps=["Step 1"],
        rollback_guidance="Rollback steps",
        approval_status="PENDING_APPROVAL"
    )
    db_session.add(rec)
    db_session.commit()
    
    client.headers.update({"Authorization": f"Bearer {data['admin_token']}"})
    resp = client.post(f"/api/v1/recommendations/{rec.id}/reject", json={"rationale": "Too risky"})
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "REJECTED"

def test_validation_failed_cannot_be_approved(client: TestClient, db_session: Session):
    data = setup_test_data(db_session)
    
    rec = Recommendation(
        id=uuid.uuid4(),
        investigation_id=data["investigation"].id,
        incident_id=data["incident"].id,
        hypothesis_id=data["hypothesis"].id,
        title="Test Rec",
        description="Test desc",
        rationale="Test rat",
        recommendation_type="CONFIGURATION_CHANGE",
        target_service_id=data["service"].id,
        expected_effect="Fixes it",
        risk_level="LOW",
        confidence=0.9,
        preconditions=[],
        validation_steps=["Step 1"],
        rollback_guidance="Rollback steps",
        approval_status="VALIDATION_FAILED"
    )
    db_session.add(rec)
    db_session.commit()
    
    client.headers.update({"Authorization": f"Bearer {data['manager_token']}"})
    resp = client.post(f"/api/v1/recommendations/{rec.id}/approve", json={"rationale": "Try it"})
    assert resp.status_code == 400
    assert "VALIDATION_FAILED" in resp.json()["detail"]

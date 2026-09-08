import pytest
from uuid import UUID, uuid4
from sqlalchemy.exc import IntegrityError

from app.services.models import Service
from app.auth.models import User, Role
from app.auth.security import get_password_hash, create_access_token
from app.auth.seed import seed_rbac

# --- Database Tests ---

def test_service_creation_and_model(db_session):
    service = Service(name="test-service", environment="production")
    db_session.add(service)
    db_session.commit()
    
    assert isinstance(service.id, UUID)
    assert service.is_active is True
    assert service.created_at is not None
    assert service.updated_at is not None
    assert service.owner_team is None

def test_service_unique_name_environment(db_session):
    s1 = Service(name="api-gateway", environment="staging")
    db_session.add(s1)
    db_session.commit()
    
    s2 = Service(name="api-gateway", environment="staging")
    db_session.add(s2)
    with pytest.raises(IntegrityError):
        db_session.commit()

# --- Helpers ---

def setup_user_with_role(db_session, role_name):
    seed_rbac(db_session)
    user = User(username=f"user_{role_name.lower().replace(' ', '_')}", email=f"{role_name.lower().replace(' ', '_')}@test.com", hashed_password=get_password_hash("pass"))
    role = db_session.query(Role).filter(Role.name == role_name).first()
    user.roles.append(role)
    db_session.add(user)
    db_session.commit()
    return user, create_access_token(data={"sub": str(user.id)})

@pytest.fixture
def admin_token(db_session):
    _, token = setup_user_with_role(db_session, "Administrator")
    return token

@pytest.fixture
def viewer_token(db_session):
    _, token = setup_user_with_role(db_session, "Viewer")
    return token

# --- API Tests ---

def test_create_service_validation(client, admin_token):
    # Missing name
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"environment": "prod"})
    assert response.status_code == 422
    
    # Missing environment
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "my-service"})
    assert response.status_code == 422
    
    # Blank name / whitespace trimming
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "   ", "environment": "prod"})
    assert response.status_code == 422
    
    # Name > 100 chars
    long_name = "a" * 101
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": long_name, "environment": "prod"})
    assert response.status_code == 422
    
    # Environment > 50 chars
    long_env = "a" * 51
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "svc", "environment": long_env})
    assert response.status_code == 422
    
    # Owner team > 100 chars
    long_owner = "a" * 101
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "svc", "environment": "prod", "owner_team": long_owner})
    assert response.status_code == 422
    
    # Description > 255 chars
    long_desc = "a" * 256
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "svc", "environment": "prod", "description": long_desc})
    assert response.status_code == 422

def test_create_service_success(client, admin_token):
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={
        "name": "   Auth Service   ", 
        "environment": "  STAGING  "
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Auth Service"
    assert data["environment"] == "staging" # normalized to lowercase
    assert data["is_active"] is True
    assert "id" in data

def test_create_duplicate_service(client, admin_token):
    client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "dup", "environment": "prod"})
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "dup", "environment": "prod"})
    assert response.status_code == 409

def test_get_service(client, viewer_token, admin_token):
    create_resp = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "get-test", "environment": "prod"})
    svc_id = create_resp.json()["id"]
    
    response = client.get(f"/api/v1/services/{svc_id}", headers={"Authorization": f"Bearer {viewer_token}"})
    assert response.status_code == 200
    assert response.json()["name"] == "get-test"

def test_get_nonexistent_service(client, viewer_token):
    response = client.get(f"/api/v1/services/{uuid4()}", headers={"Authorization": f"Bearer {viewer_token}"})
    assert response.status_code == 404

def test_get_invalid_uuid(client, viewer_token):
    response = client.get("/api/v1/services/not-a-uuid", headers={"Authorization": f"Bearer {viewer_token}"})
    assert response.status_code == 422

def test_list_services(client, admin_token, viewer_token):
    client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "list1", "environment": "prod"})
    client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "list2", "environment": "staging"})
    
    response = client.get("/api/v1/services", headers={"Authorization": f"Bearer {viewer_token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    
    response = client.get("/api/v1/services?environment=staging", headers={"Authorization": f"Bearer {viewer_token}"})
    assert response.status_code == 200
    data = response.json()
    assert all(s["environment"] == "staging" for s in data)

def test_update_service(client, admin_token):
    create_resp = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "patch-test", "environment": "prod"})
    svc_id = create_resp.json()["id"]
    
    response = client.patch(f"/api/v1/services/{svc_id}", headers={"Authorization": f"Bearer {admin_token}"}, json={
        "description": "new description",
        "owner_team": "Team A"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "patch-test" # Unchanged
    assert data["description"] == "new description"
    assert data["owner_team"] == "Team A"

def test_lifecycle_archive_reactivate(client, admin_token, viewer_token):
    create_resp = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "life-test", "environment": "prod"})
    svc_id = create_resp.json()["id"]
    
    # Archive
    patch_resp = client.patch(f"/api/v1/services/{svc_id}", headers={"Authorization": f"Bearer {admin_token}"}, json={"is_active": False})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False
    
    # Query archived (remains queryable)
    get_resp = client.get(f"/api/v1/services/{svc_id}", headers={"Authorization": f"Bearer {viewer_token}"})
    assert get_resp.json()["is_active"] is False
    
    # Reactivate
    reactivate_resp = client.patch(f"/api/v1/services/{svc_id}", headers={"Authorization": f"Bearer {admin_token}"}, json={"is_active": True})
    assert reactivate_resp.status_code == 200
    assert reactivate_resp.json()["is_active"] is True

def test_delete_endpoint_does_not_exist(client, admin_token):
    create_resp = client.post("/api/v1/services", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "del-test", "environment": "prod"})
    svc_id = create_resp.json()["id"]
    
    response = client.delete(f"/api/v1/services/{svc_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 405

# --- RBAC Tests ---

def test_rbac_unauthenticated(client):
    response = client.post("/api/v1/services", json={"name": "anon", "environment": "prod"})
    assert response.status_code == 401

def test_rbac_viewer_cannot_mutate(client, viewer_token):
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {viewer_token}"}, json={"name": "anon", "environment": "prod"})
    assert response.status_code == 403

def test_rbac_engineer_cannot_mutate(client, db_session):
    _, eng_token = setup_user_with_role(db_session, "Engineer")
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {eng_token}"}, json={"name": "anon", "environment": "prod"})
    assert response.status_code == 403

def test_rbac_incident_manager_cannot_mutate(client, db_session):
    _, mgr_token = setup_user_with_role(db_session, "Incident Manager")
    response = client.post("/api/v1/services", headers={"Authorization": f"Bearer {mgr_token}"}, json={"name": "anon", "environment": "prod"})
    assert response.status_code == 403

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import os
import jwt
from datetime import timedelta

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.auth.models import User, Role, Permission
from app.auth.security import get_password_hash, verify_password, create_access_token
from app.auth.seed import seed_rbac, LOCKED_ROLES
from app.core.config import settings
from fastapi import Depends
from app.auth.dependencies import require_role, require_permission



def test_password_hashing():
    pwd = "supersecretpassword123!"
    hashed = get_password_hash(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrongpassword", hashed) is False

def test_user_creation_and_model(db_session):
    user = User(username="testuser", email="test@test.com", hashed_password="hsh")
    db_session.add(user)
    db_session.commit()
    assert user.id is not None
    assert user.is_active is True

def test_role_and_permission_assignment(db_session):
    role = Role(name="TestRole")
    perm = Permission(name="test:read")
    user = User(username="testuser", email="test@test.com", hashed_password="hsh")
    
    role.permissions.append(perm)
    user.roles.append(role)
    db_session.add_all([user, role, perm])
    db_session.commit()
    
    assert user.roles[0].name == "TestRole"
    assert user.roles[0].permissions[0].name == "test:read"

def test_rbac_seed_is_idempotent(db_session):
    seed_rbac(db_session)
    role_count_1 = db_session.query(Role).count()
    perm_count_1 = db_session.query(Permission).count()
    
    seed_rbac(db_session)
    role_count_2 = db_session.query(Role).count()
    perm_count_2 = db_session.query(Permission).count()
    
    assert role_count_1 == role_count_2 == 4
    assert perm_count_1 == perm_count_2

def test_login_success(client, db_session):
    db_session.add(User(username="admin", email="admin@test.com", hashed_password=get_password_hash("password123")))
    db_session.commit()
    
    response = client.post("/auth/login", json={"username": "admin", "password": "password123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_invalid_credentials(client, db_session):
    db_session.add(User(username="admin", email="admin@test.com", hashed_password=get_password_hash("password123")))
    db_session.commit()
    
    response = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401
    
    response = client.post("/auth/login", json={"username": "wronguser", "password": "password123"})
    assert response.status_code == 401

def test_login_inactive_user(client, db_session):
    db_session.add(User(username="admin", email="admin@test.com", hashed_password=get_password_hash("password123"), is_active=False))
    db_session.commit()
    
    response = client.post("/auth/login", json={"username": "admin", "password": "password123"})
    assert response.status_code == 401

def test_access_token_generation_and_validation(client, db_session):
    user = User(username="admin", email="admin@test.com", hashed_password=get_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    
    token = create_access_token(data={"sub": str(user.id)})
    
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "admin"

def test_invalid_token_rejected(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer invalidtoken123"})
    assert response.status_code == 401

def test_expired_token_rejected(client, db_session):
    user = User(username="admin", email="admin@test.com", hashed_password=get_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    
    token = create_access_token(data={"sub": str(user.id)}, expires_delta=timedelta(seconds=-1))
    
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401

def test_missing_token(client):
    response = client.get("/auth/me")
    assert response.status_code == 401

@app.get("/test/require-admin", dependencies=[Depends(require_role(["Administrator"]))])
def test_endpoint_role():
    return {"status": "ok"}
    
@app.get("/test/require-perm", dependencies=[Depends(require_permission("users:read"))])
def test_endpoint_perm():
    return {"status": "ok"}

def test_unauthorized_role_rejected(client, db_session):
    seed_rbac(db_session)
    user = User(username="viewer", email="v@test.com", hashed_password=get_password_hash("pass"))
    viewer_role = db_session.query(Role).filter(Role.name == "Viewer").first()
    user.roles.append(viewer_role)
    db_session.add(user)
    db_session.commit()
    
    token = create_access_token(data={"sub": str(user.id)})
    response = client.get("/test/require-admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role privileges"

def test_authorized_role_succeeds(client, db_session):
    seed_rbac(db_session)
    user = User(username="admin", email="a@test.com", hashed_password=get_password_hash("pass"))
    admin_role = db_session.query(Role).filter(Role.name == "Administrator").first()
    user.roles.append(admin_role)
    db_session.add(user)
    db_session.commit()
    
    token = create_access_token(data={"sub": str(user.id)})
    response = client.get("/test/require-admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

def test_unauthorized_permission_rejected(client, db_session):
    seed_rbac(db_session)
    # Give viewer role which does NOT have users:read
    user = User(username="viewer", email="v@test.com", hashed_password=get_password_hash("pass"))
    viewer_role = db_session.query(Role).filter(Role.name == "Viewer").first()
    user.roles.append(viewer_role)
    db_session.add(user)
    db_session.commit()
    
    token = create_access_token(data={"sub": str(user.id)})
    response = client.get("/test/require-perm", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403

def test_authorized_permission_succeeds(client, db_session):
    seed_rbac(db_session)
    # Admin has users:read
    user = User(username="admin", email="a@test.com", hashed_password=get_password_hash("pass"))
    admin_role = db_session.query(Role).filter(Role.name == "Administrator").first()
    user.roles.append(admin_role)
    db_session.add(user)
    db_session.commit()
    
    token = create_access_token(data={"sub": str(user.id)})
    response = client.get("/test/require-perm", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

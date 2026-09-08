import pytest
import uuid
from app.detection.models import DetectorConfig
from app.auth.models import User, Role
from app.auth.security import get_password_hash, create_access_token
from app.auth.seed import seed_rbac

def get_admin_token(db_session):
    seed_rbac(db_session)
    user = User(username="admin_det", email="ad@test.com", hashed_password=get_password_hash("pass"))
    admin_role = db_session.query(Role).filter(Role.name == "Admin").first()
    # If "Admin" is not there, maybe it's "Administrator"? Check seed_rbac
    if not admin_role:
        admin_role = db_session.query(Role).filter(Role.name == "Administrator").first()
    
    # Wait, the router checks require_role(["Admin", "Engineer"]).
    # If the system uses "Administrator", I should ensure I add the name that the router expects.
    # I'll just manually add an "Admin" role if it doesn't exist.
    if not admin_role:
        admin_role = Role(name="Admin")
        db_session.add(admin_role)
        
    user.roles.append(admin_role)
    db_session.add(user)
    db_session.commit()
    return create_access_token(data={"sub": str(user.id)})

def test_create_detector_config(client, db_session):
    token = get_admin_token(db_session)
    
    # Create service
    from app.services.models import Service
    svc = Service(name="API Test Service", environment="test")
    db_session.add(svc)
    db_session.commit()

    payload = {
        "service_id": str(svc.id),
        "detector_type": "API Latency",
        "feature": "http.server.duration",
        "aggregation_function": "percentile_cont(0.95) within group (order by metric_value)",
        "min_raw_samples": 5,
        "min_baseline_observations": 12,
        "cooldown_windows": 3,
        "config": {"z_threshold": 4.0}
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/v1/detection/configs", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["version"] == 1
    assert data["enabled"] is True

def test_update_detector_config(client, db_session):
    token = get_admin_token(db_session)
    
    from app.services.models import Service
    svc = Service(name="Update Test Service", environment="test")
    db_session.add(svc)
    db_session.commit()
    
    cfg = DetectorConfig(
        service_id=svc.id,
        detector_type="Memory Leak",
        feature="memory_usage",
        aggregation_function="AVG(metric_value)",
        config={"z_threshold": 3.0},
        enabled=True,
        version=1
    )
    db_session.add(cfg)
    db_session.commit()
    
    payload = {
        "service_id": str(svc.id),
        "detector_type": "Memory Leak",
        "feature": "memory_usage",
        "aggregation_function": "AVG(metric_value)",
        "config": {"z_threshold": 4.5} # Updated
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    response = client.put(f"/api/v1/detection/configs/{cfg.id}", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    assert data["version"] == 2
    assert data["config"]["z_threshold"] == 4.5
    
    # Old config should be disabled
    db_session.refresh(cfg)
    assert cfg.enabled is False

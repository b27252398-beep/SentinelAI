from sqlalchemy.orm import Session
from app.auth.models import Role, Permission, User
from app.auth.security import get_password_hash
import logging
import os

logger = logging.getLogger(__name__)

LOCKED_ROLES = {
    "Administrator": {
        "description": "Full administrative access.",
        "permissions": ["users:read", "users:create", "users:update", "users:delete", "services:read", "services:manage", "audit:read", "incidents:read", "incidents:manage", "telemetry:read", "investigations:read", "investigations:run", "recommendations:read", "recommendations:approve"]
    },
    "Incident Manager": {
        "description": "Manage incidents and assignments.",
        "permissions": ["incidents:read", "incidents:manage", "telemetry:read", "investigations:read", "recommendations:read"]
    },
    "Engineer": {
        "description": "Access incidents and investigations.",
        "permissions": ["incidents:read", "telemetry:read", "investigations:read", "investigations:run", "recommendations:read"]
    },
    "Viewer": {
        "description": "Read-only access.",
        "permissions": ["incidents:read", "telemetry:read", "investigations:read", "recommendations:read", "audit:read"]
    }
}

def seed_rbac(db: Session):
    logger.info("Seeding RBAC roles and permissions...")
    
    # 1. Seed Permissions
    all_perms = set()
    for role_data in LOCKED_ROLES.values():
        all_perms.update(role_data["permissions"])
        
    for perm_name in all_perms:
        perm = db.query(Permission).filter(Permission.name == perm_name).first()
        if not perm:
            db.add(Permission(name=perm_name))
    
    db.commit()
    
    # 2. Seed Roles and assign permissions
    for role_name, role_data in LOCKED_ROLES.items():
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            role = Role(name=role_name, description=role_data["description"])
            db.add(role)
            db.commit()
            db.refresh(role)
            
        # Update permissions
        role.permissions = [] # clear and reset
        for perm_name in role_data["permissions"]:
            perm = db.query(Permission).filter(Permission.name == perm_name).first()
            if perm:
                role.permissions.append(perm)
                
    db.commit()
    logger.info("RBAC seeding complete.")

def seed_initial_admin(db: Session):
    admin_username = os.getenv("INITIAL_ADMIN_USERNAME")
    admin_password = os.getenv("INITIAL_ADMIN_PASSWORD")
    admin_email = os.getenv("INITIAL_ADMIN_EMAIL", "admin@sentinelai.local")
    
    if not admin_username or not admin_password:
        logger.info("No initial admin credentials provided in environment. Skipping admin seed.")
        return
        
    admin = db.query(User).filter(User.username == admin_username).first()
    if not admin:
        logger.info(f"Creating initial admin user: {admin_username}")
        admin = User(
            username=admin_username,
            email=admin_email,
            hashed_password=get_password_hash(admin_password),
            is_active=True
        )
        db.add(admin)
        
        admin_role = db.query(Role).filter(Role.name == "Administrator").first()
        if admin_role:
            admin.roles.append(admin_role)
            
        db.commit()

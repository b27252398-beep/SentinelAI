import uuid
from sqlalchemy import Column, String, Boolean, Table, ForeignKey, DateTime, Uuid
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Uuid, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)
)

class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    roles = relationship("Role", secondary=user_roles, back_populates="users")

class Role(Base):
    __tablename__ = "roles"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)

    users = relationship("User", secondary=user_roles, back_populates="roles")
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")

class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)

    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")

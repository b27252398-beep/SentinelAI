import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Uuid, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base

class Service(Base):
    __tablename__ = "services"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(String(255), nullable=True)
    environment = Column(String(50), nullable=False, index=True)
    owner_team = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('name', 'environment', name='uq_service_name_environment'),
    )

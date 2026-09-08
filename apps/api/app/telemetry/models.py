import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Uuid, UniqueConstraint, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db.base import Base

class MachineCredential(Base):
    __tablename__ = "machine_credentials"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    service_id = Column(Uuid, ForeignKey("services.id", ondelete="CASCADE"), nullable=True, index=True)
    key_prefix = Column(String(16), unique=True, nullable=False, index=True)
    api_key_hash = Column(String(64), nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(Uuid, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), primary_key=True)
    service_id = Column(Uuid, nullable=False, index=True)
    ingestion_timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    telemetry_type = Column(String(20), nullable=False)
    trace_id = Column(String(32), nullable=True, index=True)
    span_id = Column(String(16), nullable=True)
    parent_span_id = Column(String(16), nullable=True)
    severity_number = Column(Integer, nullable=True)
    metric_name = Column(String(255), nullable=True)
    metric_value = Column(Float, nullable=True)
    unit = Column(String(50), nullable=True)
    fingerprint = Column(String(64), nullable=False)
    
    resource_attributes = Column(JSONB().with_variant(String, "sqlite"), nullable=True)
    event_attributes = Column(JSONB().with_variant(String, "sqlite"), nullable=True)
    raw_payload = Column(JSONB().with_variant(String, "sqlite"), nullable=False)

    __table_args__ = (
        UniqueConstraint('fingerprint', 'timestamp', name='uq_telemetry_fingerprint_timestamp'),
        {'postgresql_partition_by': 'RANGE (timestamp)'}
    )

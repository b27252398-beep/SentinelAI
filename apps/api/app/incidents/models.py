import uuid
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Uuid, Integer,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.sql import func
from app.db.base import Base


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    service_id = Column(
        Uuid, ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    severity = Column(String(20), nullable=False)       # P1/P2/P3/P4
    status = Column(String(20), nullable=False, index=True)
    # Detected/Investigating/Identified/Mitigating/Resolved/Closed
    assigned_to = Column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    version = Column(Integer, nullable=False, default=1)
    detected_at = Column(DateTime(timezone=True), nullable=False)
    last_anomaly_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    __table_args__ = (
        Index("ix_incidents_severity", "severity"),
        # Note: partial unique index uq_active_incident_per_service
        # is created in the Alembic migration via op.execute() because
        # SQLAlchemy UniqueConstraint does not support WHERE clauses.
    )


class IncidentAnomaly(Base):
    __tablename__ = "incident_anomalies"

    incident_id = Column(
        Uuid, ForeignKey("incidents.id", ondelete="CASCADE"),
        primary_key=True, nullable=False
    )
    anomaly_id = Column(
        Uuid, ForeignKey("anomaly_events.id", ondelete="CASCADE"),
        primary_key=True, nullable=False
    )
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Each anomaly belongs to at most one incident.
        # Partial unique index uq_incident_primary_anomaly is in migration.
        UniqueConstraint("anomaly_id", name="uq_incident_anomaly_id"),
    )


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    incident_id = Column(
        Uuid, ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    event_type = Column(String(50), nullable=False)
    # incident_creation / anomaly_attached / severity_upgraded /
    # status_changed / assigned / comment_added
    actor_user_id = Column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    payload = Column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=dict
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_incident_events_created_at", "created_at"),
    )

import uuid
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Uuid, Integer, Float,
    ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.sql import func
from app.db.base import Base


class Investigation(Base):
    __tablename__ = "investigations"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    incident_id = Column(
        Uuid, ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    status = Column(String(20), nullable=False, index=True)
    # pending, running, complete, failed

    prompt_version = Column(String(100), nullable=True)
    model_identifier = Column(String(100), nullable=True)

    rca_status = Column(String(20), nullable=False, default="pending")
    # pending, accepted, rejected
    rca_reviewed_by = Column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class InvestigationEvidence(Base):
    __tablename__ = "investigation_evidence"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    investigation_id = Column(
        Uuid, ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    source_type = Column(String(20), nullable=False)
    # anomaly, log, metric, trace

    source_identifier = Column(String(128), nullable=False) 
    # UUID for anomaly/telemetry, or trace_id/span_id

    timestamp = Column(DateTime(timezone=True), nullable=False)
    service_id = Column(Uuid, ForeignKey("services.id", ondelete="CASCADE"), nullable=True)
    
    deep_copied_payload = Column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_inv_evidence_inv_source", "investigation_id", "source_identifier"),
    )


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    investigation_id = Column(
        Uuid, ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    statement = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=False)
    is_probable_root_cause = Column(Boolean, nullable=False, default=False)
    
    supporting_evidence_ids = Column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )
    contradicting_evidence_ids = Column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )




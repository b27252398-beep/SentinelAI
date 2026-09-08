import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Uuid, UniqueConstraint, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.sql import func
from app.db.base import Base

class DetectorConfig(Base):
    __tablename__ = "detector_configs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    service_id = Column(Uuid, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    detector_type = Column(String(50), nullable=False)
    feature = Column(String(100), nullable=False)
    aggregation_function = Column(String(50), nullable=False)
    min_raw_samples = Column(Integer, nullable=False, default=1)
    min_baseline_observations = Column(Integer, nullable=False, default=12)
    cooldown_windows = Column(Integer, nullable=False, default=3)
    config = Column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=1)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('service_id', 'detector_type', 'feature', 'version', name='uq_detector_logical_version'),
        Index('ix_detector_configs_logical', 'service_id', 'detector_type', 'feature'),
    )


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    service_id = Column(Uuid, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    detector_config_id = Column(Uuid, ForeignKey("detector_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    config_version = Column(Integer, nullable=False)
    detector_type = Column(String(50), nullable=False)
    feature = Column(String(100), nullable=False)
    
    window_start = Column(DateTime(timezone=True), nullable=False, index=True)
    window_end = Column(DateTime(timezone=True), nullable=False)
    
    severity = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, index=True)
    cooldown_count = Column(Integer, nullable=False, default=0)
    
    evidence = Column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('service_id', 'detector_config_id', 'config_version', 'feature', 'window_start', name='uq_anomaly_identity'),
        Index('ix_anomaly_service_window', 'service_id', 'window_start'),
    )

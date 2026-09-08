from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Any, Dict, List
from uuid import UUID
from datetime import datetime

class DetectorConfigBase(BaseModel):
    detector_type: str
    feature: str
    aggregation_function: str
    min_raw_samples: int = 1
    min_baseline_observations: int = 12
    cooldown_windows: int = 3
    config: Dict[str, Any]
    enabled: bool = True

class DetectorConfigCreate(DetectorConfigBase):
    service_id: UUID

class DetectorConfigResponse(DetectorConfigBase):
    id: UUID
    service_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AnomalyEventResponse(BaseModel):
    id: UUID
    service_id: UUID
    detector_config_id: UUID
    config_version: int
    detector_type: str
    feature: str
    window_start: datetime
    window_end: datetime
    severity: str
    status: str
    cooldown_count: int
    evidence: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class BaselineStats(BaseModel):
    mean: float
    stddev: float
    observation_count: int

class DetectionResult(BaseModel):
    is_anomaly: bool
    severity: Optional[str] = None
    evidence: Dict[str, Any]

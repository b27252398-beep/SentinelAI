from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Any, Dict
from uuid import UUID
from datetime import datetime


class IncidentCreate(BaseModel):
    """Manual incident creation payload."""
    title: str = Field(..., max_length=255)
    summary: Optional[str] = None
    service_id: UUID
    severity: str  # P1/P2/P3/P4


class IncidentUpdate(BaseModel):
    """
    PATCH incident payload.
    'version' is required for Optimistic Concurrency Control.
    """
    version: int                       # current version — stale if mismatched
    status: Optional[str] = None
    severity: Optional[str] = None
    assigned_to: Optional[UUID] = None
    summary: Optional[str] = None


class IncidentResponse(BaseModel):
    id: UUID
    title: str
    summary: Optional[str]
    service_id: UUID
    severity: str
    status: str
    assigned_to: Optional[UUID]
    version: int
    detected_at: datetime
    last_anomaly_at: datetime
    resolved_at: Optional[datetime]
    closed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class IncidentAnomalyResponse(BaseModel):
    incident_id: UUID
    anomaly_id: UUID
    is_primary: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class IncidentEventCreate(BaseModel):
    """Manual timeline comment payload."""
    comment: str


class IncidentEventResponse(BaseModel):
    id: UUID
    incident_id: UUID
    event_type: str
    actor_user_id: Optional[UUID]
    payload: Dict[str, Any]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

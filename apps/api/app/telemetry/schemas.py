from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta, timezone

class TelemetryEvent(BaseModel):
    service_id: UUID
    timestamp: datetime
    telemetry_type: str = Field(..., max_length=20)
    trace_id: Optional[str] = Field(None, max_length=32)
    span_id: Optional[str] = Field(None, max_length=16)
    parent_span_id: Optional[str] = Field(None, max_length=16)
    severity_number: Optional[int] = None
    metric_name: Optional[str] = Field(None, max_length=255)
    metric_value: Optional[float] = None
    unit: Optional[str] = Field(None, max_length=50)
    resource_attributes: Optional[Dict[str, Any]] = None
    event_attributes: Optional[Dict[str, Any]] = None
    raw_payload: Dict[str, Any]

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp_window(cls, v: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        
        lower_bound = now - timedelta(days=7)
        upper_bound = now + timedelta(days=2)
        
        if not (lower_bound <= v <= upper_bound):
            raise ValueError(f"Timestamp {v} is outside the supported window (T-7 to T+2)")
        return v
        
    @field_validator('telemetry_type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ['log', 'metric', 'trace']:
            raise ValueError("telemetry_type must be log, metric, or trace")
        return v
        
    @field_validator('trace_id', 'span_id', 'parent_span_id')
    @classmethod
    def validate_hex(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                int(v, 16)
            except ValueError:
                raise ValueError("Must be a valid hex string")
        return v
        
    @field_validator('resource_attributes', 'event_attributes', 'raw_payload', mode='before')
    @classmethod
    def parse_sqlite_json(cls, v):
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except:
                pass
        return v

class TelemetryBatch(BaseModel):
    events: List[TelemetryEvent] = Field(..., max_length=1000)

class TelemetryIngestResponse(BaseModel):
    accepted: int
    duplicates: int

class TelemetryResponse(TelemetryEvent):
    id: UUID
    ingestion_timestamp: datetime
    fingerprint: str
    model_config = ConfigDict(from_attributes=True)
    
class MachineCredentialCreate(BaseModel):
    name: str = Field(..., max_length=100)
    service_id: Optional[UUID] = None

class MachineCredentialResponse(BaseModel):
    id: UUID
    name: str
    service_id: Optional[UUID]
    key_prefix: str
    is_active: bool
    created_at: datetime
    revoked_at: Optional[datetime]
    secret: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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
    http_status_code: Optional[int] = Field(None, exclude=True)
    span_kind: Optional[str] = Field(None, exclude=True)
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

    @model_validator(mode='before')
    @classmethod
    def extract_semantics(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # http_status_code
            if data.get('http_status_code') is None:
                evt = data.get('event_attributes') or {}
                if isinstance(evt, str):
                    import json
                    try:
                        evt = json.loads(evt)
                    except:
                        evt = {}
                raw = data.get('raw_payload') or {}
                if isinstance(raw, str):
                    import json
                    try:
                        raw = json.loads(raw)
                    except:
                        raw = {}
                
                status = evt.get('http.response.status_code') or evt.get('http.status_code')
                if status is None:
                    attrs = raw.get('attributes') or {}
                    status = attrs.get('http.response.status_code') or attrs.get('http.status_code')
                
                if status is not None:
                    try:
                        data['http_status_code'] = int(status)
                    except (ValueError, TypeError):
                        pass

            # Always derive span_kind strictly from payload
            raw = data.get('raw_payload') or {}
            if isinstance(raw, str):
                import json
                try:
                    raw = json.loads(raw)
                except:
                    raw = {}
            kind = raw.get('kind') or raw.get('spanKind')
            if kind is not None:
                if isinstance(kind, int) or str(kind).isdigit():
                    kind_map = {1: 'INTERNAL', 2: 'SERVER', 3: 'CLIENT', 4: 'PRODUCER', 5: 'CONSUMER'}
                    data['span_kind'] = kind_map.get(int(kind))
                else:
                    val = str(kind).upper().replace('SPAN_KIND_', '')
                    if val in ['CLIENT', 'SERVER', 'PRODUCER', 'CONSUMER', 'INTERNAL']:
                        data['span_kind'] = val
                    else:
                        data['span_kind'] = None
            else:
                data['span_kind'] = None
                            
        return data

class TelemetryBatch(BaseModel):
    events: List[TelemetryEvent] = Field(..., max_length=1000)

class TelemetryIngestResponse(BaseModel):
    accepted: int
    duplicates: int

class TelemetryResponse(TelemetryEvent):
    id: UUID
    ingestion_timestamp: datetime
    fingerprint: str
    http_status_code: Optional[int] = None
    span_kind: Optional[str] = None
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

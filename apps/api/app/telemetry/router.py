import hashlib
import json
import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import select, exc
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.session import get_db
from app.telemetry.models import Telemetry, MachineCredential
from app.telemetry.schemas import (
    TelemetryBatch, TelemetryIngestResponse, TelemetryResponse,
    MachineCredentialCreate, MachineCredentialResponse
)
from app.telemetry.auth import verify_machine_credential, generate_api_key, hash_secret
from app.services.models import Service

from app.auth.dependencies import get_current_user, require_role

router = APIRouter()

async def enforce_payload_size(request: Request):
    content_length = request.headers.get("content-length")
    if content_length:
        if int(content_length) > 5 * 1024 * 1024:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload Too Large (Exceeds 5 MiB)")
    body = await request.body()
    if len(body) > 5 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload Too Large (Exceeds 5 MiB)")

def compute_fingerprint(event, raw_payload_json: str) -> str:
    payload_hash = hashlib.sha256(raw_payload_json.encode()).hexdigest()
    
    components = [
        str(event.service_id),
        event.timestamp.isoformat(),
        event.telemetry_type,
        event.trace_id or "",
        event.span_id or "",
        payload_hash
    ]
    
    fingerprint_str = "".join(components)
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()

@router.post("/ingest", response_model=TelemetryIngestResponse, status_code=status.HTTP_200_OK)
def ingest_telemetry(
    batch: TelemetryBatch,
    db: Session = Depends(get_db),
    cred: MachineCredential = Depends(verify_machine_credential)
):
    if not batch.events:
        return TelemetryIngestResponse(accepted=0, duplicates=0)

    service_ids = {e.service_id for e in batch.events}
    
    if cred.service_id is not None:
        for sid in service_ids:
            if sid != cred.service_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Credential is not authorized for service {sid}"
                )
    
    services = db.query(Service).filter(Service.id.in_(service_ids)).all()
    service_map = {s.id: s for s in services}
    
    for sid in service_ids:
        if sid not in service_map:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Service {sid} not found"
            )
        if not service_map[sid].is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Service {sid} is inactive or archived"
            )
            
    bind = db.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    
    values = []
    for event in batch.events:
        raw_json = json.dumps(event.raw_payload, sort_keys=True)
        fingerprint = compute_fingerprint(event, raw_json)
        
        res_attr = event.resource_attributes
        evt_attr = event.event_attributes
        r_payload = event.raw_payload
        
        if is_sqlite:
            if res_attr is not None:
                res_attr = json.dumps(res_attr)
            if evt_attr is not None:
                evt_attr = json.dumps(evt_attr)
            r_payload = json.dumps(r_payload)
        
        values.append({
            "id": uuid.uuid4(),
            "timestamp": event.timestamp,
            "service_id": event.service_id,
            "telemetry_type": event.telemetry_type,
            "trace_id": event.trace_id,
            "span_id": event.span_id,
            "parent_span_id": event.parent_span_id,
            "severity_number": event.severity_number,
            "metric_name": event.metric_name,
            "metric_value": event.metric_value,
            "unit": event.unit,
            "fingerprint": fingerprint,
            "resource_attributes": res_attr,
            "event_attributes": evt_attr,
            "raw_payload": r_payload
        })

    if bind.dialect.name == 'postgresql':
        stmt = pg_insert(Telemetry.__table__).values(values)
        stmt = stmt.on_conflict_do_nothing(index_elements=['fingerprint', 'timestamp'])
    else:
        stmt = sqlite_insert(Telemetry.__table__).values(values)
        stmt = stmt.on_conflict_do_nothing(index_elements=['fingerprint', 'timestamp'])
        
    result = db.execute(stmt)
    db.commit()
    
    accepted = result.rowcount if result.rowcount >= 0 else 0
    # In some drivers rowcount might be -1 if it can't tell, fallback
    if accepted > len(values):
        accepted = len(values)
    
    return TelemetryIngestResponse(
        accepted=accepted, 
        duplicates=len(values) - accepted
    )

@router.get("", response_model=List[TelemetryResponse])
def get_telemetry(
    service_id: Optional[uuid.UUID] = None,
    telemetry_type: Optional[str] = None,
    trace_id: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    query = db.query(Telemetry)
    if service_id:
        query = query.filter(Telemetry.service_id == service_id)
    if telemetry_type:
        query = query.filter(Telemetry.telemetry_type == telemetry_type)
    if trace_id:
        query = query.filter(Telemetry.trace_id == trace_id)
        
    query = query.order_by(Telemetry.timestamp.desc()).offset(offset).limit(limit)
    return query.all()

@router.get("/{id}", response_model=TelemetryResponse)
def get_telemetry_by_id(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    telemetry = db.query(Telemetry).filter(Telemetry.id == id).first()
    if not telemetry:
        raise HTTPException(status_code=404, detail="Telemetry not found")
    return telemetry
    
@router.post("/credentials", response_model=MachineCredentialResponse, status_code=status.HTTP_201_CREATED)
def create_credential(
    cred_in: MachineCredentialCreate,
    db: Session = Depends(get_db),
    user = Depends(require_role(["Administrator"]))
):
    prefix, secret = generate_api_key()
    
    cred = MachineCredential(
        name=cred_in.name,
        service_id=cred_in.service_id,
        key_prefix=prefix,
        api_key_hash=hash_secret(secret)
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    
    resp = MachineCredentialResponse.model_validate(cred)
    resp.secret = secret
    return resp

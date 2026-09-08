from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

# --- Shared Base Schemas ---

class InvestigationBase(BaseModel):
    status: str
    rca_status: str

class InvestigationResponse(InvestigationBase):
    id: UUID
    incident_id: UUID
    prompt_version: Optional[str] = None
    model_identifier: Optional[str] = None
    rca_reviewed_by: Optional[UUID] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class InvestigationEvidenceResponse(BaseModel):
    id: UUID
    investigation_id: UUID
    source_type: str
    source_identifier: str
    timestamp: datetime
    service_id: Optional[UUID] = None
    deep_copied_payload: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True

class HypothesisResponse(BaseModel):
    id: UUID
    investigation_id: UUID
    statement: str
    confidence: float
    reasoning: str
    is_probable_root_cause: bool
    supporting_evidence_ids: List[UUID]
    contradicting_evidence_ids: List[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class RCAActionRequest(BaseModel):
    # Empty body for accept, maybe rational for reject?
    # Design says: engineer can accept/reject RCA.
    rationale: Optional[str] = None

class RetryRequest(BaseModel):
    pass

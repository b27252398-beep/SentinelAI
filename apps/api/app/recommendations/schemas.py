from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID

class RecommendationBase(BaseModel):
    title: str
    description: str
    rationale: str
    recommendation_type: str
    target_service_id: UUID
    expected_effect: str
    risk_level: str
    confidence: float
    preconditions: List[str]
    validation_steps: List[str]
    rollback_guidance: str

class RecommendationCreate(RecommendationBase):
    pass

class RecommendationResponse(RecommendationBase):
    id: UUID
    investigation_id: UUID
    incident_id: UUID
    hypothesis_id: UUID
    approval_status: str
    execution_status: str
    decided_at: Optional[datetime] = None
    decided_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)

class RecommendationDecision(BaseModel):
    rationale: str = Field(..., min_length=1)

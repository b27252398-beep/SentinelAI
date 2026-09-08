from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime

class ServiceBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    environment: str = Field(..., max_length=50)
    owner_team: Optional[str] = Field(None, max_length=100)

    @field_validator('name', 'environment', 'owner_team')
    @classmethod
    def trim_whitespace(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError('Field cannot be empty or just whitespace')
        return v

    @field_validator('environment')
    @classmethod
    def normalize_environment(cls, v: str) -> str:
        return v.lower()

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    environment: Optional[str] = Field(None, max_length=50)
    owner_team: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None

    @field_validator('name', 'environment', 'owner_team')
    @classmethod
    def trim_whitespace(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError('Field cannot be empty or just whitespace')
        return v
        
    @field_validator('environment')
    @classmethod
    def normalize_environment(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return v.lower()
        return v

class ServiceResponse(ServiceBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

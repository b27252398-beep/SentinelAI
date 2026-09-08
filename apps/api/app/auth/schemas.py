from pydantic import BaseModel, EmailStr, ConfigDict
from typing import List, Optional

class PermissionSchema(BaseModel):
    name: str

    model_config = ConfigDict(from_attributes=True)

class RoleSchema(BaseModel):
    name: str
    permissions: List[PermissionSchema] = []

    model_config = ConfigDict(from_attributes=True)

from uuid import UUID

class UserResponse(BaseModel):
    id: UUID
    username: str
    email: EmailStr
    is_active: bool
    roles: List[RoleSchema] = []

    model_config = ConfigDict(from_attributes=True)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

class LoginRequest(BaseModel):
    username: str
    password: str

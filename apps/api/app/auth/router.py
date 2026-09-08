from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from app.db.session import get_db
from app.auth.schemas import LoginRequest, TokenResponse, UserResponse
from app.auth.models import User
from app.auth.security import verify_password, create_access_token
from app.core.config import settings
from app.auth.dependencies import get_current_user
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    # Generic error mapping to prevent user enumeration
    generic_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        # Dummy verification to mitigate timing attacks slightly
        verify_password(request.password, "$argon2id$v=19$m=65536,t=3,p=4$dummyhashformitigationpurposesss$dummyhashformitigationpurposesss")
        raise generic_error
        
    if not verify_password(request.password, user.hashed_password):
        raise generic_error
        
    if not user.is_active:
        logger.warning(f"Inactive user attempted login: {request.username}")
        raise generic_error
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    """Fetch current user details."""
    return current_user

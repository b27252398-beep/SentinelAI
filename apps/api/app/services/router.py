from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from uuid import UUID

from app.db.session import get_db
from app.auth.models import User
from app.auth.dependencies import get_current_user, require_role
from app.services.models import Service
from app.services.schemas import ServiceCreate, ServiceUpdate, ServiceResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["Services"])

@router.get("", response_model=List[ServiceResponse])
def list_services(
    environment: Optional[str] = Query(None, description="Filter by environment"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["Administrator", "Incident Manager", "Engineer", "Viewer"]))
):
    query = db.query(Service)
    if environment is not None:
        query = query.filter(Service.environment == environment.lower())
    if is_active is not None:
        query = query.filter(Service.is_active == is_active)
    
    return query.all()

@router.get("/{service_id}", response_model=ServiceResponse)
def get_service(
    service_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["Administrator", "Incident Manager", "Engineer", "Viewer"]))
):
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service

@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
def create_service(
    service_in: ServiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["Administrator"]))
):
    try:
        service = Service(**service_in.model_dump())
        db.add(service)
        db.commit()
        db.refresh(service)
        
        # AUDIT HOOK:
        # TODO: Emit audit event here
        # actor_user_id = current_user.id
        # action = "service_created"
        # target_service_id = service.id
        # after_state = service_in.model_dump()
        
        return service
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A service with this name already exists in the given environment"
        )

@router.patch("/{service_id}", response_model=ServiceResponse)
def update_service(
    service_id: UUID,
    service_update: ServiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["Administrator"]))
):
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        
    update_data = service_update.model_dump(exclude_unset=True)
    
    # AUDIT HOOK:
    # TODO: Prepare before_state for audit logging
    # before_state = {c.name: getattr(service, c.name) for c in service.__table__.columns}
    
    for field, value in update_data.items():
        setattr(service, field, value)
        
    try:
        db.commit()
        db.refresh(service)
        
        # AUDIT HOOK:
        # TODO: Emit audit event here
        # actor_user_id = current_user.id
        # action = "service_updated" (or "service_archived" if is_active changed to False)
        # target_service_id = service.id
        # after_state = update_data
        
        return service
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A service with this name already exists in the given environment"
        )

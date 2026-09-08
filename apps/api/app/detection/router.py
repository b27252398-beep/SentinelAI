from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
from uuid import UUID

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_role
from app.auth.models import User
from app.services.models import Service
from app.detection.models import DetectorConfig, AnomalyEvent
from app.detection.schemas import DetectorConfigCreate, DetectorConfigResponse, AnomalyEventResponse

router = APIRouter()

@router.post("/configs", response_model=DetectorConfigResponse, status_code=status.HTTP_201_CREATED)
def create_detector_config(
    config_in: DetectorConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["Administrator", "Engineer"]))
):
    # Verify service exists
    service = db.execute(select(Service).where(Service.id == config_in.service_id)).scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
        
    # Check if active config already exists for this combination
    existing = db.execute(
        select(DetectorConfig).where(
            DetectorConfig.service_id == config_in.service_id,
            DetectorConfig.detector_type == config_in.detector_type,
            DetectorConfig.feature == config_in.feature,
            DetectorConfig.enabled == True
        )
    ).scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="Active detector already exists for this feature. Use update instead.")
        
    new_config = DetectorConfig(
        service_id=config_in.service_id,
        detector_type=config_in.detector_type,
        feature=config_in.feature,
        aggregation_function=config_in.aggregation_function,
        min_raw_samples=config_in.min_raw_samples,
        min_baseline_observations=config_in.min_baseline_observations,
        cooldown_windows=config_in.cooldown_windows,
        config=config_in.config,
        enabled=True,
        version=1
    )
    db.add(new_config)
    db.commit()
    db.refresh(new_config)
    return new_config

@router.put("/configs/{config_id}", response_model=DetectorConfigResponse)
def update_detector_config(
    config_id: UUID,
    config_in: DetectorConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["Administrator", "Engineer"]))
):
    old_config = db.execute(select(DetectorConfig).where(DetectorConfig.id == config_id)).scalar_one_or_none()
    if not old_config:
        raise HTTPException(status_code=404, detail="Config not found")
        
    if not old_config.enabled:
        raise HTTPException(status_code=400, detail="Cannot update a disabled config")
        
    if (old_config.service_id != config_in.service_id or 
        old_config.detector_type != config_in.detector_type or 
        old_config.feature != config_in.feature):
        raise HTTPException(status_code=400, detail="Cannot change logical identity (service, type, feature) during update")
        
    # Disable old config
    old_config.enabled = False
    
    # Create new config with incremented version
    new_config = DetectorConfig(
        service_id=old_config.service_id,
        detector_type=old_config.detector_type,
        feature=old_config.feature,
        aggregation_function=config_in.aggregation_function,
        min_raw_samples=config_in.min_raw_samples,
        min_baseline_observations=config_in.min_baseline_observations,
        cooldown_windows=config_in.cooldown_windows,
        config=config_in.config,
        enabled=True,
        version=old_config.version + 1
    )
    db.add(old_config)
    db.add(new_config)
    db.commit()
    db.refresh(new_config)
    return new_config

@router.get("/configs", response_model=List[DetectorConfigResponse])
def get_detector_configs(
    service_id: UUID = None,
    enabled: bool = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(DetectorConfig)
    if service_id:
        query = query.where(DetectorConfig.service_id == service_id)
    if enabled is not None:
        query = query.where(DetectorConfig.enabled == enabled)
        
    configs = db.execute(query).scalars().all()
    return configs

@router.get("/configs/{config_id}", response_model=DetectorConfigResponse)
def get_detector_config(
    config_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    config = db.execute(select(DetectorConfig).where(DetectorConfig.id == config_id)).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    return config

@router.get("/anomalies", response_model=List[AnomalyEventResponse])
def get_anomalies(
    service_id: UUID = None,
    status: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(AnomalyEvent)
    if service_id:
        query = query.where(AnomalyEvent.service_id == service_id)
    if status:
        query = query.where(AnomalyEvent.status == status)
        
    anomalies = db.execute(query.order_by(AnomalyEvent.created_at.desc())).scalars().all()
    return anomalies

@router.get("/anomalies/{anomaly_id}", response_model=AnomalyEventResponse)
def get_anomaly(
    anomaly_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    anomaly = db.execute(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id)).scalar_one_or_none()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return anomaly

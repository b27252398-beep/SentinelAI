from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from uuid import UUID

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_role
from app.auth.models import User
from app.services.models import Service
from app.detection.models import DetectorConfig, AnomalyEvent
from app.detection.schemas import DetectorConfigCreate, DetectorConfigResponse, AnomalyEventResponse

router = APIRouter()

# Authorized detector types — deferred types must be explicitly rejected.
AUTHORIZED_DETECTOR_TYPES = {"DB Connection Exhaustion", "Memory Leak", "API Latency"}


# ---------------------------------------------------------------------------
# Detector Configuration Endpoints  →  /api/v1/detectors
# ---------------------------------------------------------------------------

@router.post("/detectors", response_model=DetectorConfigResponse, status_code=status.HTTP_201_CREATED)
def create_detector_config(
    config_in: DetectorConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["Administrator", "Engineer"]))
):
    """Create a new detector configuration (version 1). Administrator and Engineer only."""
    # Reject deferred and unknown detector types.
    if config_in.detector_type not in AUTHORIZED_DETECTOR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported detector_type '{config_in.detector_type}'. "
                f"Authorized types: {sorted(AUTHORIZED_DETECTOR_TYPES)}"
            )
        )

    # Verify service exists.
    service = db.execute(
        select(Service).where(Service.id == config_in.service_id)
    ).scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    # Reject if an active config already exists for this logical identity.
    existing = db.execute(
        select(DetectorConfig).where(
            DetectorConfig.service_id == config_in.service_id,
            DetectorConfig.detector_type == config_in.detector_type,
            DetectorConfig.feature == config_in.feature,
            DetectorConfig.enabled == True
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An active detector already exists for this (service, type, feature). Use the update endpoint."
        )

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
    try:
        db.add(new_config)
        db.commit()
        db.refresh(new_config)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A detector configuration with this identity already exists (concurrent creation)."
        )
    return new_config


@router.put("/detectors/{detector_id}", response_model=DetectorConfigResponse)
def update_detector_config(
    detector_id: UUID,
    config_in: DetectorConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["Administrator", "Engineer"]))
):
    """
    Update a detector configuration by creating an immutable new version.
    The old version is disabled. Administrator and Engineer only.
    """
    if config_in.detector_type not in AUTHORIZED_DETECTOR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported detector_type '{config_in.detector_type}'. "
                f"Authorized types: {sorted(AUTHORIZED_DETECTOR_TYPES)}"
            )
        )

    old_config = db.execute(
        select(DetectorConfig).where(DetectorConfig.id == detector_id)
    ).scalar_one_or_none()
    if not old_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detector configuration not found")

    if not old_config.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update a disabled (superseded) configuration."
        )

    if (old_config.service_id != config_in.service_id
            or old_config.detector_type != config_in.detector_type
            or old_config.feature != config_in.feature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the logical identity (service_id, detector_type, feature) during an update."
        )

    old_config.enabled = False
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
    try:
        db.add(old_config)
        db.add(new_config)
        db.commit()
        db.refresh(new_config)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Version conflict: a concurrent update already created this version. Please retry."
        )
    return new_config


@router.get("/detectors", response_model=List[DetectorConfigResponse])
def list_detector_configs(
    service_id: Optional[UUID] = None,
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List detector configurations. All authenticated human users."""
    query = select(DetectorConfig)
    if service_id is not None:
        query = query.where(DetectorConfig.service_id == service_id)
    if enabled is not None:
        query = query.where(DetectorConfig.enabled == enabled)
    configs = db.execute(query.order_by(DetectorConfig.created_at.desc())).scalars().all()
    return configs


@router.get("/detectors/{detector_id}", response_model=DetectorConfigResponse)
def get_detector_config(
    detector_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single detector configuration by ID. All authenticated human users."""
    config = db.execute(
        select(DetectorConfig).where(DetectorConfig.id == detector_id)
    ).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detector configuration not found")
    return config


# ---------------------------------------------------------------------------
# Anomaly Event Endpoints  →  /api/v1/anomalies
# ---------------------------------------------------------------------------

@router.get("/anomalies", response_model=List[AnomalyEventResponse])
def list_anomalies(
    service_id: Optional[UUID] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List anomaly events. All authenticated human users."""
    query = select(AnomalyEvent)
    if service_id is not None:
        query = query.where(AnomalyEvent.service_id == service_id)
    if status is not None:
        query = query.where(AnomalyEvent.status == status)
    anomalies = db.execute(
        query.order_by(AnomalyEvent.window_start.desc())
    ).scalars().all()
    return anomalies


@router.get("/anomalies/{anomaly_id}", response_model=AnomalyEventResponse)
def get_anomaly(
    anomaly_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single anomaly event by ID. All authenticated human users."""
    anomaly = db.execute(
        select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id)
    ).scalar_one_or_none()
    if not anomaly:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly event not found")
    return anomaly

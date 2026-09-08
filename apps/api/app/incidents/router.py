"""
Incident Management API Router.

Endpoints:
  GET    /api/v1/incidents               — list (all authenticated)
  GET    /api/v1/incidents/{id}          — detail (all authenticated)
  POST   /api/v1/incidents               — manual create (Administrator, Incident Manager)
  PATCH  /api/v1/incidents/{id}          — update (Administrator, Incident Manager, Engineer*)
  GET    /api/v1/incidents/{id}/timeline — list events (all authenticated)
  POST   /api/v1/incidents/{id}/timeline — add comment (Administrator, Incident Manager, Engineer)

*Engineer may not Close an incident.

OCC: PATCH requires `version` matching the current version. Stale → HTTP 409.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_role
from app.auth.models import User
from app.services.models import Service
from app.incidents.models import Incident, IncidentAnomaly, IncidentEvent
from app.incidents.schemas import (
    IncidentCreate,
    IncidentUpdate,
    IncidentResponse,
    IncidentAnomalyResponse,
    IncidentEventCreate,
    IncidentEventResponse,
)
from app.incidents.lifecycle import (
    is_valid_transition,
    VALID_SEVERITIES,
    VALID_STATUSES,
)
from app.incidents.correlation import _append_event

router = APIRouter()

_ADMIN_IM = ["Administrator", "Incident Manager"]
_RESPONDERS = ["Administrator", "Incident Manager", "Engineer"]
_ALL_ROLES = ["Administrator", "Incident Manager", "Engineer", "Viewer"]


# ---------------------------------------------------------------------------
# GET /incidents
# ---------------------------------------------------------------------------

@router.get("/incidents", response_model=List[IncidentResponse])
def list_incidents(
    service_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List incidents. All authenticated users."""
    q = select(Incident)
    if service_id is not None:
        q = q.where(Incident.service_id == service_id)
    if status is not None:
        q = q.where(Incident.status == status)
    if severity is not None:
        q = q.where(Incident.severity == severity)
    q = q.order_by(Incident.created_at.desc())
    return db.execute(q).scalars().all()


# ---------------------------------------------------------------------------
# GET /incidents/{id}
# ---------------------------------------------------------------------------

@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get incident by ID. All authenticated users."""
    incident = db.execute(
        select(Incident).where(Incident.id == incident_id)
    ).scalar_one_or_none()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )
    return incident


# ---------------------------------------------------------------------------
# POST /incidents — manual creation
# ---------------------------------------------------------------------------

@router.post(
    "/incidents",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ADMIN_IM)),
):
    """Manual incident creation. Administrator and Incident Manager only."""
    # Validate severity
    if payload.severity not in VALID_SEVERITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid severity '{payload.severity}'. Valid: {sorted(VALID_SEVERITIES)}",
        )

    # Verify service exists
    svc = db.execute(
        select(Service).where(Service.id == payload.service_id)
    ).scalar_one_or_none()
    if not svc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )

    now_utc = datetime.now(timezone.utc)
    incident = Incident(
        title=payload.title,
        summary=payload.summary,
        service_id=payload.service_id,
        severity=payload.severity,
        status="Detected",
        version=1,
        detected_at=now_utc,
        last_anomaly_at=now_utc,
    )
    try:
        db.add(incident)
        db.flush()
        _append_event(
            db, incident.id, "incident_creation",
            actor_user_id=current_user.id,
            payload={"created_manually": True, "severity": payload.severity},
        )
        db.commit()
        db.refresh(incident)
        return incident
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active incident already exists for this service.",
        )


# ---------------------------------------------------------------------------
# PATCH /incidents/{id}
# ---------------------------------------------------------------------------

@router.patch("/incidents/{incident_id}", response_model=IncidentResponse)
def update_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_RESPONDERS)),
):
    """
    Update incident status, severity, assignment, or summary.
    Requires current `version` for Optimistic Concurrency Control.

    Engineer may not Close an incident.
    """
    incident = db.execute(
        select(Incident).where(Incident.id == incident_id)
    ).scalar_one_or_none()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )

    # OCC version check
    if incident.version != payload.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Version conflict: expected version {incident.version}, "
                f"got {payload.version}. Re-fetch and retry."
            ),
        )

    user_roles = [r.name for r in current_user.roles]

    # Status transition
    if payload.status is not None:
        new_status = payload.status
        if new_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status '{new_status}'. Valid: {sorted(VALID_STATUSES)}",
            )
        # Engineer cannot Close
        if new_status == "Closed" and "Engineer" in user_roles and not any(
            r in user_roles for r in _ADMIN_IM
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Engineers are not permitted to close incidents.",
            )
        if not is_valid_transition(incident.status, new_status):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid transition '{incident.status}' → '{new_status}'."
                ),
            )
        old_status = incident.status
        incident.status = new_status

        # Set resolved_at / closed_at timestamps
        now_utc = datetime.now(timezone.utc)
        if new_status == "Resolved" and incident.resolved_at is None:
            incident.resolved_at = now_utc
        if new_status == "Closed" and incident.closed_at is None:
            incident.closed_at = now_utc
        # Reopen: clear resolved_at
        if new_status == "Investigating" and old_status == "Resolved":
            incident.resolved_at = None

        _append_event(
            db, incident.id, "status_changed",
            actor_user_id=current_user.id,
            payload={"old_status": old_status, "new_status": new_status},
        )

    # Severity update (manual override — does not enforce rank direction)
    if payload.severity is not None:
        if payload.severity not in VALID_SEVERITIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid severity '{payload.severity}'.",
            )
        old_sev = incident.severity
        incident.severity = payload.severity
        if old_sev != payload.severity:
            _append_event(
                db, incident.id, "severity_changed",
                actor_user_id=current_user.id,
                payload={"old_severity": old_sev, "new_severity": payload.severity},
            )

    # Assignment update
    if payload.assigned_to is not None:
        old_assigned = incident.assigned_to
        incident.assigned_to = payload.assigned_to
        _append_event(
            db, incident.id, "assigned",
            actor_user_id=current_user.id,
            payload={
                "old_assigned_to": str(old_assigned) if old_assigned else None,
                "new_assigned_to": str(payload.assigned_to),
            },
        )

    # Summary update
    if payload.summary is not None:
        incident.summary = payload.summary

    # OCC increment
    incident.version += 1

    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


# ---------------------------------------------------------------------------
# GET /incidents/{id}/anomalies
# ---------------------------------------------------------------------------

@router.get(
    "/incidents/{incident_id}/anomalies",
    response_model=List[IncidentAnomalyResponse],
)
def list_incident_anomalies(
    incident_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List anomalies attached to an incident. All authenticated users."""
    incident = db.execute(
        select(Incident).where(Incident.id == incident_id)
    ).scalar_one_or_none()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )
    anomalies = db.execute(
        select(IncidentAnomaly)
        .where(IncidentAnomaly.incident_id == incident_id)
        .order_by(IncidentAnomaly.created_at.asc())
    ).scalars().all()
    return anomalies


# ---------------------------------------------------------------------------
# GET /incidents/{id}/timeline
# ---------------------------------------------------------------------------

@router.get(
    "/incidents/{incident_id}/timeline",
    response_model=List[IncidentEventResponse],
)
def get_incident_timeline(
    incident_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get incident event timeline. All authenticated users."""
    incident = db.execute(
        select(Incident).where(Incident.id == incident_id)
    ).scalar_one_or_none()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )
    events = db.execute(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.created_at.asc())
    ).scalars().all()
    return events


# ---------------------------------------------------------------------------
# POST /incidents/{id}/timeline — add manual comment
# ---------------------------------------------------------------------------

@router.post(
    "/incidents/{incident_id}/timeline",
    response_model=IncidentEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_timeline_comment(
    incident_id: UUID,
    payload: IncidentEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_RESPONDERS)),
):
    """Add a manual comment to the incident timeline. Administrator, Incident Manager, Engineer."""
    incident = db.execute(
        select(Incident).where(Incident.id == incident_id)
    ).scalar_one_or_none()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )

    evt = IncidentEvent(
        incident_id=incident_id,
        event_type="comment_added",
        actor_user_id=current_user.id,
        payload={"comment": payload.comment},
    )
    db.add(evt)
    db.commit()
    db.refresh(evt)
    return evt

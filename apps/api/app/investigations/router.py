from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_role
from app.auth.models import User
from app.incidents.models import Incident
from app.investigations.models import Investigation, InvestigationEvidence, Hypothesis, Recommendation
from app.investigations.schemas import InvestigationResponse, InvestigationEvidenceResponse, HypothesisResponse, RCAActionRequest
from app.investigations.worker import process_investigation
from app.audit.logger import log_event

router = APIRouter()

# --- Helpers ---

def get_incident_or_404(db: Session, incident_id: UUID) -> Incident:
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident

def get_investigation_or_404(db: Session, investigation_id: UUID) -> Investigation:
    inv = db.query(Investigation).filter(Investigation.id == investigation_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return inv

# --- Endpoints ---

@router.post(
    "/incidents/{incident_id}/investigations",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=InvestigationResponse,
    dependencies=[Depends(require_role(["Administrator", "Incident Manager", "Engineer"]))]
)
def start_investigation(
    incident_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Starts a new investigation for an incident."""
    incident = get_incident_or_404(db, incident_id)
    
    # Check if one is already pending or running
    active = db.query(Investigation).filter(
        Investigation.incident_id == incident.id,
        Investigation.status.in_(["pending", "running"])
    ).first()
    
    if active:
        raise HTTPException(status_code=409, detail="An investigation is already active for this incident.")
        
    inv = Investigation(
        incident_id=incident.id,
        status="pending"
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    
    log_event("investigation_created", current_user.id, inv.id)
    background_tasks.add_task(process_investigation, inv.id)
    return inv


@router.post(
    "/investigations/{investigation_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=InvestigationResponse,
    dependencies=[Depends(require_role(["Administrator", "Incident Manager", "Engineer"]))]
)
def retry_investigation(
    investigation_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retries a failed investigation by spawning a new one."""
    failed_inv = get_investigation_or_404(db, investigation_id)
    if failed_inv.status != "failed":
        raise HTTPException(status_code=400, detail="Only failed investigations can be retried.")
        
    # Same logic as start_investigation
    incident = get_incident_or_404(db, failed_inv.incident_id)
    active = db.query(Investigation).filter(
        Investigation.incident_id == incident.id,
        Investigation.status.in_(["pending", "running"])
    ).first()
    
    if active:
        raise HTTPException(status_code=409, detail="An investigation is already active for this incident.")
        
    inv = Investigation(
        incident_id=incident.id,
        status="pending"
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    
    log_event("investigation_retried", current_user.id, inv.id, {"previous_id": str(failed_inv.id)})
    background_tasks.add_task(process_investigation, inv.id)
    return inv


@router.get(
    "/incidents/{incident_id}/investigations",
    response_model=List[InvestigationResponse],
    dependencies=[Depends(require_role(["Administrator", "Incident Manager", "Engineer", "Viewer"]))]
)
def list_investigations_for_incident(
    incident_id: UUID,
    db: Session = Depends(get_db)
):
    get_incident_or_404(db, incident_id)
    return db.query(Investigation).filter(Investigation.incident_id == incident_id).order_by(Investigation.created_at.desc()).all()


@router.get(
    "/investigations/{investigation_id}",
    response_model=InvestigationResponse,
    dependencies=[Depends(require_role(["Administrator", "Incident Manager", "Engineer", "Viewer"]))]
)
def get_investigation(
    investigation_id: UUID,
    db: Session = Depends(get_db)
):
    return get_investigation_or_404(db, investigation_id)


@router.get(
    "/investigations/{investigation_id}/evidence",
    response_model=List[InvestigationEvidenceResponse],
    dependencies=[Depends(require_role(["Administrator", "Incident Manager", "Engineer", "Viewer"]))]
)
def get_investigation_evidence(
    investigation_id: UUID,
    db: Session = Depends(get_db)
):
    get_investigation_or_404(db, investigation_id)
    return db.query(InvestigationEvidence).filter(InvestigationEvidence.investigation_id == investigation_id).all()


@router.get(
    "/investigations/{investigation_id}/hypotheses",
    response_model=List[HypothesisResponse],
    dependencies=[Depends(require_role(["Administrator", "Incident Manager", "Engineer", "Viewer"]))]
)
def get_investigation_hypotheses(
    investigation_id: UUID,
    db: Session = Depends(get_db)
):
    get_investigation_or_404(db, investigation_id)
    return db.query(Hypothesis).filter(Hypothesis.investigation_id == investigation_id).all()


@router.post(
    "/investigations/{investigation_id}/rca/accept",
    response_model=InvestigationResponse,
    dependencies=[Depends(require_role(["Administrator", "Incident Manager", "Engineer"]))]
)
def accept_rca(
    investigation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inv = get_investigation_or_404(db, investigation_id)
    if inv.status != "complete":
        raise HTTPException(status_code=400, detail="Investigation must be complete to accept RCA.")
    
    inv.rca_status = "accepted"
    inv.rca_reviewed_by = current_user.id
    db.commit()
    db.refresh(inv)
    
    log_event("rca_accepted", current_user.id, inv.id)
    return inv


@router.post(
    "/investigations/{investigation_id}/rca/reject",
    response_model=InvestigationResponse,
    dependencies=[Depends(require_role(["Administrator", "Incident Manager", "Engineer"]))]
)
def reject_rca(
    investigation_id: UUID,
    req: RCAActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inv = get_investigation_or_404(db, investigation_id)
    if inv.status != "complete":
        raise HTTPException(status_code=400, detail="Investigation must be complete to reject RCA.")
    
    inv.rca_status = "rejected"
    inv.rca_reviewed_by = current_user.id
    db.commit()
    db.refresh(inv)
    
    log_event("rca_rejected", current_user.id, inv.id, {"rationale": req.rationale})
    return inv

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from typing import List
from uuid import UUID
from datetime import datetime, timezone

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_role
from app.investigations.models import Investigation, Hypothesis
from app.recommendations.models import Recommendation
from app.recommendations.schemas import RecommendationResponse, RecommendationDecision
from app.recommendations.worker import generate_recommendation_task
from app.audit.logger import log_event

router = APIRouter()

@router.post("/investigations/{id}/recommendations", status_code=status.HTTP_202_ACCEPTED)
async def generate_recommendations(
    id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(["Administrator", "Incident Manager", "Engineer"]))
):
    inv = db.query(Investigation).filter(Investigation.id == id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")
        
    if inv.status != "complete":
        raise HTTPException(status_code=400, detail="Investigation is not complete")

    hyp = db.query(Hypothesis).filter(
        Hypothesis.investigation_id == id,
        Hypothesis.is_probable_root_cause == True
    ).first()

    if not hyp:
        raise HTTPException(status_code=422, detail="No probable root cause identified")

    if hyp.confidence < 0.4:
        raise HTTPException(status_code=422, detail="LOW_RCA_CONFIDENCE")

    # Pass to background task
    # Note: the task takes db=None so it creates its own session to avoid thread issues,
    # except in tests where we might run it sync
    background_tasks.add_task(generate_recommendation_task, id, None)
    
    return {"status": "accepted", "message": "Recommendation generation started"}

@router.get("/investigations/{id}/recommendations", response_model=List[RecommendationResponse])
def list_investigation_recommendations(
    id: UUID,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    recs = db.query(Recommendation).filter(Recommendation.investigation_id == id).all()
    return recs

@router.get("/recommendations/{id}", response_model=RecommendationResponse)
def get_recommendation(
    id: UUID,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    rec = db.query(Recommendation).filter(Recommendation.id == id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec

@router.post("/recommendations/{id}/approve", response_model=RecommendationResponse)
def approve_recommendation(
    id: UUID,
    decision: RecommendationDecision,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(["Administrator", "Incident Manager"]))
):
    rec = db.query(Recommendation).filter(Recommendation.id == id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
        
    if rec.approval_status != "PENDING_APPROVAL":
        raise HTTPException(status_code=400, detail=f"Cannot approve recommendation in status: {rec.approval_status}")

    rec.approval_status = "APPROVED"
    rec.decided_at = datetime.now(timezone.utc)
    rec.decided_by = user.id
    
    try:
        db.commit()
        db.refresh(rec)
        log_event("recommendation_approved", str(user.id), str(rec.id), {"rationale": decision.rationale})
        return rec
    except StaleDataError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Concurrency conflict during approval: version mismatch")
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Database constraint violation during approval")

@router.post("/recommendations/{id}/reject", response_model=RecommendationResponse)
def reject_recommendation(
    id: UUID,
    decision: RecommendationDecision,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(["Administrator", "Incident Manager"]))
):
    rec = db.query(Recommendation).filter(Recommendation.id == id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
        
    if rec.approval_status != "PENDING_APPROVAL":
        raise HTTPException(status_code=400, detail=f"Cannot reject recommendation in status: {rec.approval_status}")

    rec.approval_status = "REJECTED"
    rec.decided_at = datetime.now(timezone.utc)
    rec.decided_by = user.id
    
    try:
        db.commit()
        db.refresh(rec)
        log_event("recommendation_rejected", str(user.id), str(rec.id), {"rationale": decision.rationale})
        return rec
    except StaleDataError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Concurrency conflict during rejection: version mismatch")
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Database constraint violation during rejection")

@router.post("/recommendations/{id}/revoke", response_model=RecommendationResponse)
def revoke_recommendation(
    id: UUID,
    decision: RecommendationDecision,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(["Administrator", "Incident Manager"]))
):
    rec = db.query(Recommendation).filter(Recommendation.id == id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
        
    if rec.approval_status != "APPROVED":
        raise HTTPException(status_code=400, detail="Only approved recommendations can be revoked")

    rec.approval_status = "REVOKED"
    rec.decided_at = datetime.now(timezone.utc)
    rec.decided_by = user.id
    
    try:
        db.commit()
        db.refresh(rec)
        log_event("recommendation_revoked", str(user.id), str(rec.id), {"rationale": decision.rationale})
        return rec
    except StaleDataError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Concurrency conflict during revocation: version mismatch")
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Database constraint violation during revocation")

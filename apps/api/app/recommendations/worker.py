import asyncio
import logging
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.session import SessionLocal
from app.investigations.models import Investigation, Hypothesis, InvestigationEvidence
from app.recommendations.models import Recommendation
from app.recommendations.validator import validate_recommendation
from app.investigations.llm import get_llm_provider
from app.audit.logger import log_event
import redis

logger = logging.getLogger(__name__)

# Use strict Redis initialization. Production must not fall back to a mock lock.
# Tests that require a mock should patch `get_redis`.
redis_client = None

def get_redis():
    global redis_client
    if not redis_client:
        r = redis.Redis(host='localhost', port=6379, db=0)
        # Test connection; if it fails, it raises an exception to fail safely.
        r.ping()
        redis_client = r
    return redis_client

async def generate_recommendation_task(investigation_id: UUID, db: Session = None):
    # Using injected session for tests, otherwise create new
    session = db if db else SessionLocal()
    
    try:
        r = get_redis()
    except Exception as e:
        logger.error(f"Failed to acquire Redis connection for recommendation generation: {e}")
        log_event("recommendation_generation_failed", "System", str(investigation_id), {"reason": "Distributed locking unavailable"})
        if not db:
            session.close()
        return

    lock_key = f"lock:recommendation_generation:{str(investigation_id)}"
    
    try:
        # Use real redis-py client
        acquired = r.set(lock_key, "locked", nx=True, ex=60)
        if not acquired:
            logger.info(f"Recommendation generation for {investigation_id} is already locked.")
            return
        
        # 1. Fetch Investigation & RCA
        inv = session.query(Investigation).filter(Investigation.id == investigation_id).first()
        if not inv or inv.status != "complete":
            log_event("recommendation_generation_failed", "System", str(investigation_id), {"reason": "Investigation incomplete or missing"})
            return

        hyp = session.query(Hypothesis).filter(
            Hypothesis.investigation_id == investigation_id,
            Hypothesis.is_probable_root_cause == True
        ).first()

        if not hyp:
            log_event("recommendation_generation_failed", "System", str(investigation_id), {"reason": "No probable RCA found"})
            return
            
        if hyp.confidence < 0.4:
            log_event("recommendation_generation_failed", "System", str(investigation_id), {"reason": "LOW_RCA_CONFIDENCE blocked generation"})
            return

        # Pre-process: Supersede old PENDING_APPROVAL recommendations
        old_recs = session.query(Recommendation).filter(
            Recommendation.investigation_id == investigation_id,
            Recommendation.approval_status == "PENDING_APPROVAL"
        ).all()
        for old in old_recs:
            old.approval_status = "SUPERSEDED"
            old.updated_at = datetime.now(timezone.utc)
            log_event("recommendation_superseded", "System", str(old.id), {"investigation_id": str(investigation_id)})
        
        if old_recs:
            session.commit()

        # 2. Gather Evidence for LLM Context
        evidence_ids = hyp.supporting_evidence_ids + hyp.contradicting_evidence_ids
        evidence_records = session.query(InvestigationEvidence).filter(
            InvestigationEvidence.id.in_(evidence_ids)
        ).all()
        
        evidence_text = "===EVIDENCE_START===\n"
        for rec in evidence_records:
            evidence_text += f"[{rec.source_type}] {rec.deep_copied_payload}\n"
        evidence_text += "===EVIDENCE_END==="

        # 3. Call LLM
        provider = get_llm_provider()
        prompt = "Generate a remediation recommendation based on the RCA and evidence."
        
        try:
            llm_response = await provider.generate_recommendations(prompt, hyp.statement, evidence_text)
        except Exception as e:
            log_event("recommendation_generation_failed", "System", str(investigation_id), {"reason": str(e)})
            return

        rec_data = llm_response.recommendation
        
        # Determine risk level capping for contradicting evidence
        risk_level = rec_data.risk_level
        if hyp.contradicting_evidence_ids:
            risk_level = "HIGH"

        # 4. Create Recommendation Entity
        target_service = inv.incident_id # We need to get the real target service. We'll pull it from the incident.
        # Actually target_service is usually the one affected by the incident
        # For MVP we can just query incident's service_id
        from app.incidents.models import Incident
        incident = session.query(Incident).filter(Incident.id == inv.incident_id).first()
        target_service_id = incident.service_id if incident else None

        new_rec = Recommendation(
            investigation_id=inv.id,
            incident_id=inv.incident_id,
            hypothesis_id=hyp.id,
            title=rec_data.title,
            description=rec_data.description,
            rationale=rec_data.rationale,
            recommendation_type=rec_data.recommendation_type,
            target_service_id=target_service_id,
            expected_effect=rec_data.expected_effect,
            risk_level=risk_level,
            confidence=rec_data.confidence,
            preconditions=rec_data.preconditions,
            validation_steps=rec_data.validation_steps,
            rollback_guidance=rec_data.rollback_guidance,
            approval_status="PENDING_VALIDATION",
            execution_status="PENDING"
        )
        session.add(new_rec)
        session.commit()
        session.refresh(new_rec)
        
        log_event("recommendation_created", "System", str(new_rec.id), {"investigation_id": str(inv.id)})

        # 5. Deterministic Safety Validation
        is_safe, reason = validate_recommendation(session, new_rec)
        if is_safe:
            new_rec.approval_status = "PENDING_APPROVAL"
            new_rec.updated_at = datetime.now(timezone.utc)
            session.commit()
            log_event("recommendation_validated", "System", str(new_rec.id), {})
        else:
            new_rec.approval_status = "VALIDATION_FAILED"
            new_rec.updated_at = datetime.now(timezone.utc)
            session.commit()
            log_event("recommendation_validation_failed", "System", str(new_rec.id), {"reason": reason})

    finally:
        # Release lock
        if 'r' in locals() and 'acquired' in locals() and acquired:
            r.delete(lock_key)
        
        if not db:
            session.close()
